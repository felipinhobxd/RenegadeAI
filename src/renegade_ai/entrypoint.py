from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "autoplay":
        from renegade_ai.autoplay import main as autoplay_main

        autoplay_main(args[1:])
        return
    if args and args[0] == "scout":
        from renegade_ai.scout_cli import main as scout_main

        scout_main(args[1:])
        return
    if args and args[0] == "evolve":
        from renegade_ai.evolve_cli import main as evolve_main

        evolve_main(args[1:])
        return

    from renegade_ai.cli import main as legacy_main

    legacy_main()


if __name__ == "__main__":
    main()
