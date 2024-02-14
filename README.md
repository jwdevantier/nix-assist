Hopefully over time, a collection of tools to make debugging in Nix better

## dbgnixmod.py
This is a small tool to help debugging the writing of a nix module, by letting you write
a minimal configuration file, load it all into a nix repl session and evaluate a series
of nix expressions, printing the results to the terminal.

```nix
# example.no_nvidia.nix
{ config, lib, pkgs, ... }:
with lib;
let cfg = config.no_nvidia;
in
{
  options.no_nvidia = {
    enable = mkEnableOption "disable nvidia driver";
  };

  config = mkIf cfg.enable {
    boot.blacklistedKernelModules = [ "nvidia" ];
  };
}
```

```nix
# example.config.nix
{ ... }:
{
  imports = [ ./example.no_nvidia.nix ];
  no_nvidia.enable = true;
  boot.blacklistedKernelModules = [ "foo" ];
}
```

```
# example.replscript

# All configuration keys are prefixed by `config.`
config.no_nvidia
config.boot.blacklistedKernelModules
```


If we run:
```
./dbgnixmod.py -c example.config.nix -m example.no_nvidia.nix -x example.replscript

Evaluating:
  * conf: 'example.config.nix'
  * modules: 
    - example.no_nvidia.nix


> nix repl -f eval.nix
>>> config.no_nvidia
{ enable = true; }
>>> config.boot.blacklistedKernelModules
[ "nvidia" "foo" ]
```

If we change `example.config.nix` such that `no_nvidia.enable = false;` and re-run,
we will see that `config.boot.blacklistedKernelModules` will change:

```
./dbgnixmod.py -c example.config.nix -m example.no_nvidia.nix -x example.replscript

Evaluating:
  * conf: 'example.config.nix'
  * modules: 
    - example.no_nvidia.nix


> nix repl -f eval.nix
>>> config.no_nvidia
{ enable = true; }
>>> config.boot.blacklistedKernelModules
[ "foo" ]
```
