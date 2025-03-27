DIST := test
COMPONENT := main

define RELEASE
Origin: ebcl_build_tools
Label: RestRepo
Suite: testing
Codename: test
Version: 1.0
Architectures: amd64
Description: EBcL credentials test repository
Components: $(COMPONENT)
Date: $(shell date -Ru)
endef
export RELEASE

GPG_EMAIL := test@example.com

define GPG_PARAMS
Key-Type: 1
Key-Length: 1024
Subkey-Type: 1
Subkey-Length: 1024
Name-Real: test
Name-Email: $(GPG_EMAIL)
Expire-Date: 0
%no-ask-passphrase
%no-protection
endef
export GPG_PARAMS

GNUPGHOME = $(CURDIR)/gpg
export GNUPGHOME

all: repo/dists/$(DIST)/InRelease repo/Release.key

repo:
	mkdir -p $@

repo/Release.gpg: | repo
	mkdir -p -m 700 gpg
	echo "$$GPG_PARAMS" | gpg --batch --generate-key -
	gpg --export $(GPG_EMAIL) > $@

repo/Release.key: repo/Release.gpg
	gpg --enarmor < $< >$@

repo/cred-test-package_all.deb: | repo
	dpkg-deb --build cred-test-package $@

repo/dists/$(DIST)/$(COMPONENT)/binary-amd64/Packages: repo/cred-test-package_all.deb
	mkdir -p $(dir $@)
	dpkg-scanpackages -m -a amd64 repo /dev/null > $@
	sed -i 's~repo/~~g' $@

repo/dists/$(DIST)/$(COMPONENT)/binary-amd64/Packages.xz: repo/dists/$(DIST)/$(COMPONENT)/binary-amd64/Packages
	xz -c $^ > $@

repo/dists/$(DIST)/Release: repo/dists/$(DIST)/$(COMPONENT)/binary-amd64/Packages.xz repo/dists/$(DIST)/$(COMPONENT)/binary-amd64/Packages
	echo "$${RELEASE}" > $@
	echo "SHA256:" >> $@
	for f in $^; do \
		echo " $$(sha256sum $$f | cut -d' ' -f1) $$(wc -c $$f | sed 's~repo/dists/$(DIST)/~~')" >> $@; \
	done

repo/dists/$(DIST)/InRelease: repo/dists/$(DIST)/Release | repo/Release.gpg
	gpg --clearsign -o $@ $<

clean:
	rm -rf repo gpg
