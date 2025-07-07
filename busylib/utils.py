import ipaddress


def is_ipv4(string: str) -> bool:
    """
    Checks if a string is a valid IPv4 address.
    """
    try:
        ipaddress.IPv4Address(string)
        return True
    except ipaddress.AddressValueError:
        return False
