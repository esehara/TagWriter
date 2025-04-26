from rich import print

verbose = False

def verbose_print(msg):
    global verbose
    if verbose:
        print(msg)
