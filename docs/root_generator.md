# Root Generator

The _root generator_ is responsible for generating and conifguring a tarball of the root filesystem. The _root generator_ supports the following parameters:

- *config_file*: Path to the yaml configuration file of the root filesystem.
- *output*: Path to the folder where the generated artifacts are placed.
- *--no-config*: Skip the configuration step. This flag allows a two-step 
  build which first creates the tarball containing all selected packages,
  and then applies the use configuration.
- *--sysroot*: The sysroot flag allows to add additional packages only required
  as part of the sysroot for cross-compiling.

The core part of the _root generator_ is implemented in _ebcl/tools/root/root.py_.
The _main_ function takes care of parsing the command line parameters
and then runs _create_root_ of the _RootGenerator_ class, and finally runs
_finalize_ to cleanup temporary artifacts.

The build process implemented in *create_root* executes the following high level steps:

- In case of a sysroot build: Add additional packages to the list of selected packages.
- Create the root tarball using either _kiwi_ or _debootstrap_.
- In case of not skipping the configuration: Copy the overlays and run the config scripts.
- Move the resulting tarball to the output folder.

## Implementation details

### Root tarball generation

TODO: write section

### Root configuration

The root filesystem configuration is shared code between the _root generator_ and the _root configurator_ and is implemented in _ebcl/tools/root/__init__.py_. For configuring the root tarball the following steps are executed:

- Extract the tarball to a temporary folder.
- Copy the host files to this folder, overwriting existing files if necessary.
- Execute the configuration scripts in the given environment.
- Pack the result as tarball.

Copying of the files and running the scripts is common code for all tools and implemented in the _Files_ class contained in _ebcl/common/files.py_.

#### Copy the host files

The host files which shall be overlayed to the root filesystem are defined in the configuration file using the _host_files_ parameters. These configuration is parsed
using _parse_files_ of _ebcl/common/files.py_. For each file or folder a _source_
value is required. This source value is interpreted as relative path to the config file.
Optionally a _destination_, a _mode_, a _uid_ and a _gid_ can be given. These additional
parameters are evaluted by _copy_files_. If _uid_ and _gid_ is not given, the user id 0,
and the group id 0 is used, which means _root_ user and group. If no _mode_ is given
the _mode_ is not modified, i.e. the value is kept for the file.

#### Run the configuration scripts

TODO: write section

## Root configurator

The _root configurator_, which is implemented in _ebcl/tools/root/root_config.py_, is a stripped down version of the _root generator_, which only applies the customer specific configruation on top of an existing tarball.
