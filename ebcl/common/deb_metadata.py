"""
Classes for parsing debian metadata files
"""

from collections import defaultdict
import logging

from .deb import Package
from .types.cpu_arch import CpuArch
from .version import PackageRelation, Version, VersionDepends, parse_depends


class DebMetadata:
    """
    Parser for debian metadata files (like control, Release, Packages)

    Metadata can be organized in stanzas (or paragraphs) to define multiple
    entities in a single file. This is for example used in the Packages file
    where every stanza defines a package.

    Each stanza has a list of key-value pairs, where the value CAN span multiple lines.
    Key and value are separated by a colon and continuation lines MUST be indented by a space or a tab.
    (See: https://www.debian.org/doc/debian-policy/ch-controlfields.html#syntax-of-control-files)

    Keys in the metadata are not case sensitive, so they are storred in lower case!

    The parser automatically excludes a pgp signature.
    """
    stanzas: list[dict[str, str]]

    def __init__(self, content: str, multi_stanza=True) -> None:
        """
        Parse content into self.stanzas

        If multi_stanza is False all key value pairs are parsed into self.stanza[0].
        """
        self.stanzas = []
        cur_stanza: dict[str, str] | None = None
        cur_key: str | None = None
        for line in content.splitlines():
            # Skip pgp signature
            if line == "-----BEGIN PGP SIGNED MESSAGE-----":
                continue
            elif line == "-----BEGIN PGP SIGNATURE-----":
                break

            if not line.strip():
                cur_key = None
                if multi_stanza:
                    cur_stanza = None
                continue
            elif cur_stanza is None:
                cur_stanza = {}
                self.stanzas.append(cur_stanza)
                cur_key = None

            # continuation line
            if (line.startswith(" ") or line.startswith("\t")) and cur_key:
                cur_stanza[cur_key] += "\n" + line.strip()
            elif ":" in line:
                key, value = map(str.strip, line.split(':', 1))
                # Keys should be reqad case-insensitve, so store them lowered
                key = key.lower()
                cur_key = key
                cur_stanza[key] = value


class DebPackagesInfo:
    """Parses a debian Packages file into a list of Packages"""
    RELATIONS = [
        ("depends", PackageRelation.DEPENDS),
        ("pre-depends", PackageRelation.PRE_DEPENS),
        ("recommends", PackageRelation.RECOMMENDS),
        ("suggests", PackageRelation.SUGGESTS),
        ("enhances", PackageRelation.ENHANCES),
        ("breaks", PackageRelation.BREAKS),
        ("conflicts", PackageRelation.CONFLICTS)
    ]
    packages: list[Package]

    def __init__(self, content: str) -> None:
        """
        Parses content into a list Packages.
        Note that Package.repo is set to "filled-later" and it is the responsibility
        of the caller, to set it to am appropriate value.
        """
        meta = DebMetadata(content)
        self.packages = []
        for stanza in meta.stanzas:
            arch = CpuArch.from_str(stanza.get("architecture"))
            if arch is None:
                arch = CpuArch.UNDEFINED
            pkg = Package(stanza.get("package", ""), arch, "filled-later")
            pkg.file_url = stanza.get("filename")
            pkg.version = Version(stanza.get("version", ""))

            for key, rel in self.RELATIONS:
                value = stanza.get(key, None)
                if value is None:
                    continue
                pkg.set_relation(
                    rel,
                    self._parse_relation(pkg.name, value, rel, arch)
                )
            self.packages.append(pkg)

    def _parse_relation(
        self, name: str, relation: str, package_relation: PackageRelation, arch: CpuArch
    ) -> list[list[VersionDepends]]:
        """Parse relation string from stanza."""
        deps: list[list[VersionDepends]] = []

        for rel in relation.split(','):
            dep = parse_depends(rel.strip(), arch, package_relation)
            if dep:
                deps.append(dep)
            else:
                logging.error('Invalid package relation %s to %s for %s.',
                              rel.strip(), package_relation, name)

        return deps


class DebReleaseInfo:
    """Parses a debian Release or InRelease file."""
    CHECKSUM_KEYS = ["md5sum", "sha1", "sha256", "sha512"]
    _data: dict[str, str]
    _hashes: dict[str, list[tuple[str, int, str]]]

    def __init__(self, content: str) -> None:
        self._data = {}
        self._hashes = defaultdict(list)
        self._data = DebMetadata(content, multi_stanza=False).stanzas[0]

        for hash_key in self.CHECKSUM_KEYS:
            if hash_key in self._data:
                self._hashes[hash_key] = []
                for line in self._data[hash_key].splitlines():
                    parts = line.split()
                    if len(parts) == 3:
                        self._hashes[hash_key].append((parts[0], int(parts[1]), parts[2]))

    @property
    def components(self) -> list[str]:
        """Return the list of components defined in the Release file."""
        return self._data.get("components", "").split()

    @property
    def hashes(self) -> dict[str, list[tuple[str, int, str]]]:
        """
        Return the file hashes defined in the Release file.

        The hashes are returned as a dictionary mapping the hash algorithm
        to a list of 3-tuples with hash, file size and filename.
        """
        return self._hashes
