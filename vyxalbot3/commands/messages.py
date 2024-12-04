import os.path
import string

with open(os.path.join(os.path.split(__file__)[0], "statuses.txt")) as file:
    STATUSES = file.read().strip().splitlines()