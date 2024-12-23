# Makefile to recreate the flat repo

define IN_RELEASE_HEAD
Origin: Test Repo
Label: TestRepo
Architectures: amd64 arm64
Description: Test repo
Date: Wed Dec 11 12:00:00 2024
SHA256:
endef
export IN_RELEASE_HEAD

all: Packages.xz InRelease

Packages: $(wildcard *.deb)
	dpkg-scanpackages -m . /dev/null > Packages
	sed -i 's~./~~g' Packages

Packages.xz: Packages
	xz -c $^ > $@

InRelease:
	echo "$$IN_RELEASE_HEAD" > InRelease
	echo " $$(sha256sum Packages | cut -d' ' -f1) $$(wc -c Packages)" >> InRelease
	echo " $$(sha256sum Packages.xz | cut -d' ' -f1) $$(wc -c Packages.xz)" >> InRelease

clean:
	rm Packages* InRelease
