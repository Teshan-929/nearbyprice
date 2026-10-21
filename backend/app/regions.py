import math


def grid_region(lat: float, lon: float, dlat: float = 0.08, dlon: float = 0.12) -> str:
    """Crude neighbourhood id: a grid cell of roughly 9 x 8 km at Berlin's latitude.

    A stand-in until we use true 'stations within X km' neighbourhoods.
    """
    return f"{math.floor(lat / dlat)}_{math.floor(lon / dlon)}"
