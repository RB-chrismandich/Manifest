# Bootstrap Modules

`bootstrap.sh` supports optional extension modules loaded from `bootstrap/modules/*.sh`.

## Hook Names

Use `register_bootstrap_hook "<hook>" "<function_name>"` in your module:

- `after_config_load`
- `before_install`
- `after_deploy`
- `after_auth`
- `after_verify`

## Example Module

```bash
#!/bin/bash

my_custom_after_deploy() {
    print_info "Custom module ran after deploy"
}

register_bootstrap_hook "after_deploy" "my_custom_after_deploy"
```

Save as `bootstrap/modules/my_module.sh`. It will be auto-loaded on the next bootstrap run.
