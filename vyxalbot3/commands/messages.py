import os.path
import string

with open(os.path.join(os.path.split(__file__)[0], "statuses.txt")) as file:
    STATUSES = file.read().strip().splitlines()

HUGS = [
    "⊂((・▽・))⊃",
    "⊂(◉‿◉)つ",
    "(づ｡◕‿‿◕｡)づ",
    "༼ つ ◕_◕ ༽つ",
    "(つ ͡° ͜ʖ ͡°)つ",
    "༼ つ ◕o◕ ༽つ"
]

HELLO = [
    "hello!",
    "hi!",
    "greetings",
    "good day",
    "\\o"
]

GOODBYE = [
    "o/",
    "bye!",
    "adios",
    "au revoir"
]

RAPTOR = r"""
                                                                   YOU CAN RUN, BUT YOU CAN'T HIDE, {user}
                                                         ___._
                                                       .'  <0>'-.._
                                                      /  /.--.____")
                                                     |   \   __.-'~
                                                     |  :  -'/
                                                    /:.  :.-'
    __________                                     | : '. |
    '--.____  '--------.______       _.----.-----./      :/
            '--.__            `'----/       '-.      __ :/
                  '-.___           :           \   .'  )/
                        '---._           _.-'   ] /  _/
                             '-._      _/     _/ / _/
                                 \_ .-'____.-'__< |  \___
                                   <_______.\    \_\_---.7
                                  |   /'=r_.-'     _\\ =/
                              .--'   /            ._/'>
                            .'   _.-'
       snd                 / .--'
                          /,/
                          |/`)
                          'c=,
"""