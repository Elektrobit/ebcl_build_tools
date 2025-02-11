names := test-empty test-simple test-multiple test-ebclfsa

files_test-empty := files-empty
arch_test-empty := arm64

files_test-simple := files-ok
arch_test-simple := arm64

files_test-multiple := files-ok files-ok2
arch_test-multiple := arm64

# Reuse files from the example and include too much (expected and config) on purpose!
files_test-ebclfsa := ../examples/qemu_ebclfsa
arch_test-ebclfsa := arm64

debs := $(addsuffix .deb,$(names))
all: $(debs) Packages.xz InRelease


define gen_targets
deb := $(1)
tmp/$$(deb)/DEBIAN:
	mkdir -p $$@
tmp/$$(deb)/DEBIAN/%: %.in | tmp/$$(deb)/DEBIAN
	sed 's/@@NAME@@/$(1)/; s/@@VERSION@@/$$(VERSION)/; s/@@ARCH@@/$$(ARCH)/;' $$< > $$@
$$(deb).deb: tmp/$$(deb)/DEBIAN/control
	$$(foreach f,$(files_$(1)),cp -r $$(f)/* tmp/$$(DEB);)
	dpkg-deb -b tmp/$$(DEB) $$@
	rm -rf tmp/$$(DEB)
$$(deb).deb: VERSION=1.0
$$(deb).deb: ARCH=$(arch_$(1))
$$(deb).deb: DEB=$(1)
endef

#$(foreach name,$(names),$(info $(call gen_targets,$(name))))
$(foreach name,$(names),$(eval $(call gen_targets,$(name))))



define IN_RELEASE_HEAD
Origin: Test Repo
Label: TestRepo
Architectures: amd64 arm64
Description: Test repo
Date: Wed Dec 11 12:00:00 2024
SHA256:
endef
export IN_RELEASE_HEAD

Packages: $(debs)
	dpkg-scanpackages -m . /dev/null > Packages
	sed -i 's~./~~g' Packages

Packages.xz: Packages
	xz -c $^ > $@

InRelease:
	echo "$$IN_RELEASE_HEAD" > InRelease
	echo " $$(sha256sum Packages | cut -d' ' -f1) $$(wc -c Packages)" >> InRelease
	echo " $$(sha256sum Packages.xz | cut -d' ' -f1) $$(wc -c Packages.xz)" >> InRelease

clean:
	rm -rf tmp
	rm -rf *.deb
	rm -f Packages* InRelease
