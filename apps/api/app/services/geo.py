"""Distancias geográficas (haversine)."""
import math


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_geofence(lat: float, lng: float, point_lat: float, point_lng: float, radius_m: float) -> bool:
    return haversine_m(lat, lng, point_lat, point_lng) <= radius_m
