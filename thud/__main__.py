import sys
from . import core, ui


def main():
    args = sys.argv[1:]
    if args and args[0] == "test":
        from .selftest import selftest
        print(selftest())
        return
    if args[:2] == ["theory", "export"]:
        from . import theory
        print(theory.export())
        return
    for a in args:
        if a.endswith(".thud"):
            core.load(a)
    core.refresh()
    ui.run()


if __name__ == "__main__":
    main()
