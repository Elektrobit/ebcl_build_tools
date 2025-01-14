"""" EBcL deb package cache. """
import logging
import os
import shutil
import sqlite3

from pathlib import Path
from typing import Callable, Iterable

from . import get_cache_folder
from .deb import Package, filter_packages, DebFile, InvalidFile
from .version import PackageRelation, Version, VersionDepends, VersionRelation

from .types.cpu_arch import CpuArch


def register_sqlite_adaptors() -> None:
    """ Register conversion handlers from python classes to sqlite field values and vice versa """

    def adapt_arch(arch: CpuArch) -> str:
        return str(arch)

    def convert_arch(val: bytes) -> CpuArch:
        return CpuArch.from_str(val.decode("utf-8")) or CpuArch.UNDEFINED

    sqlite3.register_adapter(CpuArch, adapt_arch)
    sqlite3.register_converter(CpuArch.__name__, convert_arch)

    def adapt_version(version: Version) -> str:
        return str(version)

    def convert_version(value: bytes) -> Version:
        return Version(value.decode("utf-8"))

    sqlite3.register_adapter(Version, adapt_version)
    sqlite3.register_converter(Version.__name__, convert_version)

    def adapt_package_relation(relation: PackageRelation) -> str:
        return relation.name

    def convert_package_relation(value: bytes) -> PackageRelation:
        return PackageRelation[value.decode("utf-8")]

    sqlite3.register_adapter(PackageRelation, adapt_package_relation)
    sqlite3.register_converter(PackageRelation.__name__, convert_package_relation)

    def adapt_version_relation(relation: VersionRelation) -> str:
        return relation.name

    def convert_version_relation(value: bytes) -> VersionRelation | None:
        return VersionRelation[value.decode("utf-8")]

    sqlite3.register_adapter(VersionRelation, adapt_version_relation)
    sqlite3.register_converter(VersionRelation.__name__, convert_version_relation)


register_sqlite_adaptors()


class CacheBackendSqlite:
    _con: sqlite3.Connection
    _in_create: bool = False

    def __init__(self, filename: Path) -> None:
        self._con = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES)

    def create(self, scan_files: Callable[[], None]) -> None:
        """ Try to create the tables in the database if they do not exist """
        # Try to get a write lock. If that is not possible,
        # it means that some other process already has a write lock,
        # so the database is eitehr initialized or will be initialized
        # by that process
        try:
            self._con.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            return

        # If there are any tables in the database, assume it is initialized
        if self._con.execute("SELECT COUNT(*) FROM sqlite_master where type='table'").fetchone()[0] != 0:
            self._con.rollback()
            return

        try:
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS package(
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    arch CpuArch NOT NULL,
                    repo TEXT NOT NULL,
                    version Version NOT NULL,
                    url TEXT,
                    file TEXT,
                    UNIQUE (name, arch, version) ON CONFLICT ABORT,
                    UNIQUE (file)
                )
                """
            )
            # A relation can have a number of options per dependency,
            # where A | B | C, D means A, B or C and D must be fulfilled.
            # This is modeled using two tables, the first one describes the
            # and relations, while the second one containts the or relations.
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS and_relation(
                    id INTEGER PRIMARY KEY,
                    package INTEGER NOT NULL,
                    FOREIGN KEY (package) REFERENCES package(id)
                )
                """
            )
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS or_relation(
                    and_relation INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    arch CpuArch NOT NULL,
                    package_relation PackageRelation NOT NULL,
                    version_relation VersionRelation,
                    version Version,
                    FOREIGN KEY (and_relation) REFERENCES and_relation(id)
                )
                """
            )
        except sqlite3.OperationalError as e:
            # An error here means that something is wrong with the statements
            # Rollback to prevent a partially initialized database
            self._con.rollback()
            raise e

        self._in_create = True
        scan_files()
        self._in_create = False

        self._con.commit()

    def _fill_relations(self, id: int, package: Package) -> Package:
        """ Fetch relations (depends, conflicts, ...) from the database """

        # Fetch all rows for one package.
        # Two rows with the same id are from the same and-table, so they represent
        # an or-relationship (distinct lines in the and-table represent and-relationships)
        res = self._con.execute(
            """
            SELECT id, name, package_relation, version_relation, version, arch
                FROM and_relation, or_relation ON id == and_relation WHERE package == ? ORDER BY id
            """,
            (id,)
        )
        prev_id: int | None = None
        cur_entry: list[VersionDepends] = []
        out = []
        # Merge or-relationships into their own lists, to that the result
        # is a list of and-relationships being lists of or-relationships
        for row in res:
            entry = VersionDepends(
                *row[1:6]
            )
            if row[0] != prev_id:
                if cur_entry:
                    out.append(cur_entry)
                    cur_entry = []
                prev_id = row[0]
            cur_entry.append(entry)
        if cur_entry:
            out.append(cur_entry)

        package.relations = out
        return package

    def get(
        self,
        arch: CpuArch,
        name: str,
        version: Version | None = None,
        relation: VersionRelation | None = None,
    ) -> Package | None:
        """ Find a package in the database"""

        mapping: dict[int, int] = {}  # map id(Package) to sqlite id

        def package_factory(cursor: sqlite3.Cursor, row: sqlite3.Row) -> Package:
            p = Package(
                *row[1:7]
            )
            mapping[id(p)] = row[0]
            return p

        cur = self._con.cursor()
        cur.row_factory = package_factory
        # Get all packages matching the name and architecture
        cur.execute(
            """
            SELECT id, name, arch, repo, version, url, file FROM package
                WHERE name == ?
                AND   arch == ?
            """,
            (name, arch)
        )
        packages: Iterable[Package] = cur.fetchall()
        # Filter version matches
        if version is not None:
            if relation is None:
                relation = VersionRelation.LARGER
            packages = filter(lambda p: filter_packages(p, version, relation), packages)

        # Ensure cache file exists.
        packages = filter(lambda p: p.local_file and os.path.isfile(p.local_file), packages)
        packages = reversed(sorted(packages))

        package = next(iter(packages), None)
        if package:
            return self._fill_relations(mapping[id(package)], package)
        return None

    def add(self, package: Package) -> bool:
        """
        Add a package to the cache database

        @return False, if the package cannot be added
        """
        relations = list(package.relations)

        # When adding packages, while creating the daabase
        # a transaction is already active, so use savepoints
        # to allow rollback of failed insertions
        if self._in_create:
            self._con.execute("SAVEPOINT add_package")

            def savepoint_rollback() -> None:
                self._con.execute("ROLLBACK TO add_package")
                self._con.execute("RELEASE add_package")

            def savepoint_commit() -> None:
                self._con.execute("RELEASE add_package")

            rollback_cmd = savepoint_rollback
            commit_cmd = savepoint_commit
        else:
            self._con.execute("BEGIN IMMEDIATE")
            rollback_cmd = self._con.rollback
            commit_cmd = self._con.commit
        try:
            res = self._con.execute(
                """
                INSERT INTO package (name, arch, repo, version, url, file)
                VALUES(?,?,?,?,?,?)
                RETURNING id
                """,
                (
                    package.name,
                    package.arch,
                    package.repo,
                    package.version,
                    package.file_url,
                    package.local_file
                )
            )
        except sqlite3.IntegrityError:
            # Someone else added the same package in the meantime
            # or it is already in the cache
            rollback_cmd()
            return False

        package_id = res.fetchone()[0]
        res.close()

        relation_and_ids: list[int] = []
        for _ in range(len(relations)):
            try:
                res = self._con.execute(
                    "INSERT INTO and_relation (package) VALUES(?) RETURNING id",
                    (package_id, )
                )
            except sqlite3.IntegrityError:
                rollback_cmd()
                return False
            relation_and_ids.append(res.fetchone()[0])

        try:
            self._con.executemany(
                """
                INSERT INTO or_relation
                    (and_relation, name, arch, package_relation, version_relation, version)
                    VALUES(?,?,?,?,?,?)
                """,
                (
                    (
                        rid,
                        relation.name,
                        relation.arch,
                        relation.package_relation,
                        relation.version_relation,
                        relation.version
                    )
                    for rid, relation_list in zip(relation_and_ids, relations)
                    for relation in relation_list
                )
            )
        except sqlite3.IntegrityError:
            # This should never happen
            rollback_cmd()
            return False

        commit_cmd()
        return True

    def size(self) -> int:
        """ Number of entries in the cache """
        return self._con.execute("SELECT COUNT(*) FROM package").fetchone()[0]


class Cache:
    """" EBcL deb package cache. """
    _backend: CacheBackendSqlite
    _folder: Path

    def __init__(self, folder: Path | None = None) -> None:
        """ Setup the cache store. """
        self._folder = folder or Path(get_cache_folder('cache'))

        self._folder.mkdir(parents=True, exist_ok=True)
        self._backend = CacheBackendSqlite(self._folder / "index.db")

        self._backend.create(self._scan_existing_files)

    @property
    def folder(self) -> Path:
        return self._folder

    def clear(self) -> None:
        """ Clear the cache """
        del self._backend
        shutil.rmtree(self._folder)
        self._folder.mkdir()
        self._backend = CacheBackendSqlite(self._folder / "index.db")
        self._backend.create(lambda: None)

    def _scan_existing_files(self) -> None:
        """
        Scan existing files

        This method is called by the cache backend, when it creates the database
        to import existing packages into the cache.
        """

        for root, _, files in os.walk(self._folder, followlinks=False):
            files = list(filter(lambda s: s.endswith(".deb"), files))
            for file in files:
                file_path = Path(root) / file
                try:
                    package = DebFile(file_path).to_package()
                    print(package)
                except InvalidFile:
                    logging.info("File %s is invalid and will be deleted", str(file_path))
                    file_path.unlink()
                    continue
                if not self._backend.add(package):
                    logging.info("File %s cannot be added to the cache and will be deleted", str(file_path))
                    file_path.unlink()

    def add(self, package: Package, do_move: bool = False) -> str | None:
        """ Add a package to the cache. """
        logging.debug('Add package %s to cache.', package)

        if not package.version:
            logging.warning(
                'Package %s has no valid version (%s)!', package, package.version)
            return None

        if not package.local_file or not os.path.isfile(package.local_file):
            logging.warning('Package %s has no valid local file!', package)
            return None

        dst_folder = self._folder / str(package.version.epoch)
        dst_file = dst_folder / os.path.basename(package.local_file)

        old_local = package.local_file
        package.local_file = str(dst_file)
        if self._backend.add(package):
            if old_local != str(dst_file):
                if dst_file.exists():
                    logging.warning('Not overwriting deb %s.', dst_file)
                else:
                    dst_folder.mkdir(parents=True, exist_ok=True)

                    if do_move:
                        shutil.move(old_local, str(dst_file))
                    else:
                        shutil.copy(old_local, str(dst_file))
        else:
            logging.warning('Unable to add package %s to cache', dst_file)
            package.local_file = old_local

        return package.local_file

    def get(
        self,
        arch: CpuArch,
        name: str,
        version: Version | None = None,
        relation: VersionRelation | None = None,
    ) -> Package | None:
        """ Get a deb file from the cache. """
        logging.debug('Get package %s/%s/%s from cache.', name, version, arch)
        return self._backend.get(arch, name, version, relation)

    def size(self) -> int:
        return self._backend.size()

    def __str__(self) -> str:
        return f'Cache<{self._folder}>'

    def __repr__(self) -> str:
        return self.__str__()
