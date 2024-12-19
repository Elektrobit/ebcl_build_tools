""" Build tools for embedded Linux images. """
__version__ = "2.0.0"
__dependencies__ = "sudo debootstrap bash apt coreutils mount rsync tar gnupg wget " \
    "cpio findutils zstd file fakeroot fakechroot"
__ebcl_repo_key__ = "https://linux.elektrobit.com/eb-corbos-linux/ebcl_1.0_key.pub"
