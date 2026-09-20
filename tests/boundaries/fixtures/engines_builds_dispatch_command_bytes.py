# EVASION fixture (C5): the dispatcher is a socket write, so its command is as
# likely to be spelled in bytes as in str.
DISPATCH = (b"nc", b"-U", b"-q0")
