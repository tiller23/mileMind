/**
 * Unit conversion utilities for distance display.
 *
 * The backend always stores distances in km. These functions convert
 * for display when the user prefers imperial (miles).
 */

const KM_TO_MILES = 0.621371;

export function formatDistance(km: number, units: "metric" | "imperial"): string {
  if (units === "imperial") {
    const miles = km * KM_TO_MILES;
    return `${miles.toFixed(1)} mi`;
  }
  return `${km} km`;
}

export function distanceLabel(units: "metric" | "imperial"): string {
  return units === "imperial" ? "mi" : "km";
}
