#!/usr/bin/env nix-shell
#! nix-shell -i python3 -p python311 python311Packages.pexpect

import argparse
import tempfile
from contextlib import contextmanager
from pathlib import Path
import sys
import textwrap
import shutil
import pexpect


@contextmanager
def temp_dir():
    tmp = tempfile.TemporaryDirectory()
    tmpd = Path(tmp.name)
    try:
        yield tmpd
    finally:
        tmp.cleanup()


class CliParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"error: {message}\n")
        self.print_help()
        sys.exit(2)


def arg_file(arg: str) -> Path:
    p = Path(arg)
    if not p.exists():
        raise RuntimeError(f"no file at {arg!r}")
    elif not p.is_file():
        raise RuntimeError(f"path {arg!r} exists, but is not a file")
    return p


NIX_REPL_INPUT = "nix-repl>"

ex_module_no_nvidia = """\
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
""".rstrip()

ex_config = """\
{ ... }:
{
  imports = [ ./example.no_nvidia.nix ];
  no_nvidia.enable = true;
  boot.blacklistedKernelModules = [ "foo" ];
}
""".rstrip()

ex_replscript = """\
# All configuration keys are prefixed by `config.`
config.no_nvidia
config.boot.blacklistedKernelModules
""".rstrip()

epilog = textwrap.dedent(f"""\
This tool aims at reducing the drudgery of debugging Nix modules.

Specifically, this tool lets you write a *minimal* config using one
or more modules, evaluate it in `nix repl` and provide one or more
script files containing expressions to evaluate in the REPL.

This can be useful when you want to see how defining various options
alters configuration values in your config.

## Example ?
To see what this program does in action, try re-running with
'--generate-example' and follow the instructions.

## What is a (repl)script?

Replscripts are basically files where each line is taken to be a Nix
expression to be evaluated in the `nix repl` session after the configuration
file has been loaded.

These files are useful when checking a configuration involves evaluating
multiple expressions each time.
""")

def generate_example():
    cwd = Path.cwd()
    conf = cwd / "example.config.nix"
    mod = cwd / "example.no_nvidia.nix"
    replscript = cwd / "example.replscript"
    err = False
    if conf.exists():
        print(f"File config {conf.name!r} exists, aborting")
        err = True
    if mod.exists():
        print(f"File {mod.name!r} exists, aborting")
        err = True
    if replscript.exists():
        print(f"File {replscript.name!r} exists, aborting")
        err = True

    if err:
        print("\nOne or more files of the example cannot be written out because they would override existing files")
        print("Please remove them if appropriate and re-try")
        sys.exit(1)

    with open(conf, "w") as fh:
        fh.write(ex_config)
    with open(mod, "w") as fh:
        fh.write(ex_module_no_nvidia)
    with open(replscript, "w") as fh:
        fh.write(ex_replscript)

    print("Files are generated.")
    print("\nNow first run")
    print(f"./{Path(__file__).name} -c example.config.nix -x example.replscript -m example.no_nvidia.nix")
    print("")
    print("Then:")
    print("  * Open example.config.nix")
    print("  * Change 'no_nvidia.enable = true;' to 'no_nvidia.enable = false;' ")
    print("  * Re-run the command")
    print("")
    print("Note how 'boot.blacklistedKernelModules' will change in response to disabling the module.")


def main():
    parser = CliParser(
        description="Make debugging Nix modules easier by evaluating a minimal config with one or more modules used.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="debugging information"
    )

    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="use the repl directly after executing the script"
    )

    parser.add_argument(
        "--generate-example",
        action="store_true",
        help="generate an example to experiment with in the current working directory"
    )

    parser.add_argument(
        "-c", "--conf",
        type=arg_file,
        # required=True,
        help="Nix config"
    )

    parser.add_argument(
        "-x", "--script",
        nargs="+",
        type=arg_file,
        help="repl commands to run"
    )

    parser.add_argument(
        "-m", "--module",
        nargs="+",
        type=arg_file,
        # required=True,
        help="nix module"
    )

    args = parser.parse_args()
    if args.generate_example:
        generate_example()
        sys.exit(0)

    if None in (args.conf, args.module):
        parser.print_help()
        sys.exit(1)
    with temp_dir() as td:

        for module in args.module:
            if args.debug:
                print(f"\nModule {module.name!r}:")
                print("---")
                with open(module) as fh:
                    print(textwrap.indent(fh.read().rstrip(), prefix="  "))
                print("---")
            shutil.copy(str(module.resolve()), td / module.name)

        shutil.copy(args.conf, td / args.conf.name)
        if args.debug:
            print(f"\nConfiguration {args.conf.name!r}:")
            print("---")
            with open(args.conf) as fh:
                print(textwrap.indent(fh.read().rstrip(), prefix="  "))
            print("---")

        tstfile = td / "eval.nix"
        with open(tstfile, "w") as fh:
            eval_contents = f"import <nixpkgs/nixos> {{ configuration = ./{args.conf.name}; }}"
            fh.write(eval_contents)
            if args.debug:
                print("\neval.nix:")
                print("---")
                print(textwrap.indent(eval_contents, prefix="  "))
                print("---\n")

        if not args.debug:
            print(f"Evaluating:")
            print(f"  * conf: {args.conf.name!r}")
            print("  * modules: ")
            for module in args.module:
                print(f"    - {module.name}")
            print("")
        cmd = "nix repl -f eval.nix"
        print(f"\n> {cmd}")
        child = pexpect.spawn(cmd, cwd=td)
        child.expect(NIX_REPL_INPUT, timeout=10)
        for script in args.script:
            with open(script, "r") as fh:
                lines = [line.strip() for line in fh]
            for line in lines:
                line = line.strip()
                if line.startswith("#"):
                    continue
                print(">>>", end="", sep="")
                child.sendline(line)
                child.expect(NIX_REPL_INPUT, timeout=5)
                out = child.before.decode("utf-8").rstrip()
                print(out, sep="")
        if args.interactive:
            print("\nInteractive:\n------------")
            print(NIX_REPL_INPUT, sep=" ", end="")
            child.interact()

if __name__ == "__main__":
    main()

