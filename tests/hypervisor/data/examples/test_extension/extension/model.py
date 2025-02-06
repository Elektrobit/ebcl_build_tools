from ebcl.tools.hypervisor import model


class VM(model.VM):
    def finalize(self, registry: model.HVConfig) -> None:
        registry.register_module('custom_model_was_used')
        return super().finalize(registry)
