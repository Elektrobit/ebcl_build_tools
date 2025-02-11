NAME := example

versions := 1.0 1.1 2.0 1:1.0 1.0-1a 1.0-1z 1.0-10z
archs := arm64 amd64 all

debs :=

define gen_targets
deb := $(NAME)_$(subst :,+,$(1))_$(2)
debs += $$(deb).deb
all: $$(deb).deb

tmp/$$(deb)/DEBIAN:
	mkdir -p $$@
tmp/$$(deb)/DEBIAN/%: %.in | tmp/$$(deb)/DEBIAN
	sed 's/@@NAME@@/$$(NAME)/; s/@@VERSION@@/$$(VERSION)/; s/@@ARCH@@/$$(ARCH)/;' $$< > $$@
$$(deb).deb: tmp/$$(deb)/DEBIAN/control
	dpkg-deb -b tmp/$$(DEB) $$@
	rm -rf tmp/$$(DEB)
$$(deb).deb: VERSION=$(1)
$$(deb).deb: ARCH=$(2)
$$(deb).deb: DEB=$(NAME)_$(subst :,+,$(1))_$(2)
endef

$(foreach arch,$(archs),$(foreach version,$(versions),$(eval $(call gen_targets,$(version),$(arch)))))

clean:
	rm -rf tmp
	rm -rf *.deb
