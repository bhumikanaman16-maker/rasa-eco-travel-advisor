"""
EcoTravel Advisor – Rasa Custom Actions
MSc Assignment: Conversational Agent for Sustainable Tourism Planning

All external API credentials are read from environment variables.
No secrets are hard-coded or logged.
"""

import os
import json
import time
import base64
from typing import Any, Text, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction


# -----------------------------------------------------------------
# ENVIRONMENT SETUP
# -----------------------------------------------------------------

load_dotenv()

CLIMATIQ_API_KEY: Optional[str] = os.getenv("CLIMATIQ_API_KEY")
AMADEUS_API_KEY: Optional[str] = os.getenv("AMADEUS_API_KEY")
AMADEUS_API_SECRET: Optional[str] = os.getenv("AMADEUS_API_SECRET")

CLIMATIQ_TRAVEL_URL = "https://api.climatiq.io/travel/v1/distance"
AMADEUS_AUTH_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMADEUS_HOTELS_URL = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
AMADEUS_OFFERS_URL = "https://test.api.amadeus.com/v2/shopping/hotel-offers"
AMADEUS_FLIGHTS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"

# Path for local fallback data
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FALLBACK_HOTELS_PATH = os.path.join(
    _BASE_DIR, "data", "external", "fallback_hotels.json"
)
FALLBACK_ACTIVITIES_PATH = os.path.join(
    _BASE_DIR, "data", "external", "fallback_activities.json"
)
FALLBACK_FLIGHTS_PATH = os.path.join(
    _BASE_DIR, "data", "external", "fallback_flights.json"
)
CARBON_OFFSET_PROGRAMS_PATH = os.path.join(
    _BASE_DIR, "data", "external", "carbon_offset_programs.json"
)

# Transport mode CO2e reference values (kg per passenger per km)
# Used for comparative display; actual values come from Climatiq API.
TRANSPORT_CO2E_PER_KM = {
    "rail": 0.041,
    "car": 0.171,
    "air": 0.255,
}

# Sustainability thresholds for colour labels
CO2E_GREEN_THRESHOLD = 50.0    # kg CO2e – lower emissions
CO2E_AMBER_THRESHOLD = 150.0   # kg CO2e – moderate emissions


# -----------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------

def normalise_transport_mode(mode: Optional[str]) -> str:
    """
    Convert common user wording into the canonical values:
    rail | car | air
    """
    if not mode:
        return ""
    mode = mode.strip().lower()
    aliases: Dict[str, str] = {
        "train": "rail",
        "railway": "rail",
        "rail": "rail",
        "plane": "air",
        "flight": "air",
        "flying": "air",
        "airplane": "air",
        "air": "air",
        "driving": "car",
        "automobile": "car",
        "road": "car",
        "car": "car",
    }
    return aliases.get(mode, mode)


def normalise_sustainability(level: Optional[str]) -> str:
    """
    Normalise sustainability preference to: high | medium | low
    """
    if not level:
        return "medium"
    level = level.strip().lower()
    if level in ("high", "very high", "maximum", "green", "eco"):
        return "high"
    if level in ("low", "minimum", "basic", "cheap"):
        return "low"
    return "medium"


def emissions_label(co2e_kg: float) -> str:
    """
    Return a text sustainability label based on CO2e value.
    Colour labels are comparative indicators, not universal thresholds.
    """
    if co2e_kg <= CO2E_GREEN_THRESHOLD:
        return "🟢 Lower emissions"
    if co2e_kg <= CO2E_AMBER_THRESHOLD:
        return "🟡 Moderate emissions"
    return "🔴 Higher emissions"


def get_safe_api_error(response: requests.Response) -> str:
    """
    Extract a meaningful error description from an API response
    without exposing authentication data.
    """
    try:
        data = response.json()
        if isinstance(data, dict):
            for key in ("message", "error", "detail", "title", "errors"):
                val = data.get(key)
                if val:
                    if isinstance(val, list) and val:
                        return str(val[0])
                    return str(val)
    except (ValueError, KeyError):
        pass
    return f"HTTP {response.status_code}"


def load_json_file(path: str) -> Any:
    """Load JSON from a file path; return None on failure."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# -----------------------------------------------------------------
# RECOMMENDATION RANKING
# -----------------------------------------------------------------

def ranking_weights(sustainability: str) -> Dict[str, float]:
    """
    Return carbon / price / sustainability-quality weights based on
    the user's stated sustainability preference.
    """
    weights: Dict[str, Dict[str, float]] = {
        "high": {
            "carbon": 0.50,
            "price": 0.20,
            "quality": 0.30,
        },
        "medium": {
            "carbon": 0.35,
            "price": 0.35,
            "quality": 0.30,
        },
        "low": {
            "carbon": 0.20,
            "price": 0.50,
            "quality": 0.30,
        },
    }
    return weights.get(sustainability, weights["medium"])


def normalise_values(
    values: List[float],
    invert: bool = False,
) -> List[float]:
    """
    Min-max normalise a list of floats to [0, 1].
    If invert=True the lowest raw value gets the highest score.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    normed = [(v - lo) / (hi - lo) for v in values]
    if invert:
        normed = [1.0 - n for n in normed]
    return normed


def rank_hotels(
    hotels: List[Dict],
    sustainability: str,
) -> List[Dict]:
    """
    Rank hotel entries by weighted composite score.
    Each entry must have: price (float), carbon_score (float 0-10),
    sustainability_score (float 0-10).
    """
    if not hotels:
        return []

    weights = ranking_weights(sustainability)

    prices = [h.get("price", 999) for h in hotels]
    carbons = [h.get("carbon_score", 5) for h in hotels]
    qualities = [h.get("sustainability_score", 5) for h in hotels]

    norm_price = normalise_values(prices, invert=True)
    norm_carbon = normalise_values(carbons, invert=False)   # higher = already greener
    norm_quality = normalise_values(qualities, invert=False)

    scored = []
    for idx, hotel in enumerate(hotels):
        score = (
            weights["carbon"] * norm_carbon[idx]
            + weights["price"] * norm_price[idx]
            + weights["quality"] * norm_quality[idx]
        )
        scored.append({**hotel, "_score": score})

    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


# -----------------------------------------------------------------
# AMADEUS API
# -----------------------------------------------------------------

def get_amadeus_token() -> Optional[str]:
    """
    Obtain an Amadeus OAuth2 bearer token using client credentials.
    Returns the token string or None on failure.
    Never logs credentials.
    """
    if not AMADEUS_API_KEY or not AMADEUS_API_SECRET:
        return None

    try:
        resp = requests.post(
            AMADEUS_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": AMADEUS_API_KEY,
                "client_secret": AMADEUS_API_SECRET,
            },
            timeout=15,
        )
        if resp.ok:
            return resp.json().get("access_token")
    except requests.exceptions.RequestException:
        pass
    return None


def search_amadeus_hotels(
    city_code: str,
    token: str,
) -> List[Dict]:
    """
    Search for hotels in a city using the Amadeus sandbox API.
    Returns a list of hotel dicts with id, name, chain_code, etc.
    """
    try:
        resp = requests.get(
            AMADEUS_HOTELS_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "cityCode": city_code.upper(),
                "radius": 5,
                "radiusUnit": "KM",
                "amenities": "SWIMMING_POOL,SPA,FITNESS_CENTER",
                "ratings": "3,4,5",
            },
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            return data.get("data", [])
    except requests.exceptions.RequestException:
        pass
    return []


DEMO_CITY_TO_IATA: Dict[str, str] = {
    "london": "LON",
    "paris": "PAR",
    "new york": "NYC",
    "berlin": "BER",
    "madrid": "MAD",
    "rome": "ROM",
    "amsterdam": "AMS",
    "barcelona": "BCN",
    "tokyo": "TYO",
}

MONTH_MAP: Dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def resolve_iata_code(location_input: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve user location input to a 3-letter IATA code.
    Accepts 3-letter IATA codes or mapped demonstration cities.
    Returns (iata_code, error_message).
    """
    if not location_input:
        return None, "No location was specified."
    raw = str(location_input).strip()
    if len(raw) == 3 and raw.isalpha():
        return raw.upper(), None
    low = raw.lower()
    for city, code in DEMO_CITY_TO_IATA.items():
        if city in low:
            return code, None
    supported = ", ".join(c.title() for c in sorted(DEMO_CITY_TO_IATA.keys()))
    return None, (
        f"I could not map '{raw}' to a recognized airport code. "
        f"Please enter a supported city (e.g., {supported}) or a 3-letter IATA code (e.g., LON, PAR)."
    )


def parse_departure_date(dates_input: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract a valid departure date in YYYY-MM-DD format.
    Handles YYYY-MM-DD and natural language date expressions.
    Returns (iso_date_string, error_message).
    """
    if not dates_input:
        return None, "Please specify your travel departure date (e.g., YYYY-MM-DD or '10 October')."
    
    text = str(dates_input).strip()
    
    import re
    from datetime import datetime

    # 1. Direct YYYY-MM-DD match
    iso_match = re.search(r"\b(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", text)
    if iso_match:
        return iso_match.group(0), None

    # 2. Natural language match (e.g., "10 October" or "10 October to 15 October")
    pattern = r"\b(\d{1,2})\s+([A-Za-z]+)\b"
    match = re.search(pattern, text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).lower()
        month = MONTH_MAP.get(month_str)
        if month:
            current_year = 2026
            try:
                dt = datetime(current_year, month, day)
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

    return None, (
        f"Could not parse a valid departure date from '{text}'. "
        "Please enter a specific date in YYYY-MM-DD format (e.g., 2026-10-15)."
    )


def search_amadeus_flights(
    origin_code: str,
    destination_code: str,
    departure_date: str,
    token: str,
) -> Tuple[List[Dict], Optional[str], Optional[int]]:
    """
    Search for flight offers using Amadeus sandbox API v2.
    Returns (data_list, error_msg, status_code).
    Handles 400, 401/403, 429, 5xx, timeouts, DNS/network errors safely.
    """
    try:
        resp = requests.get(
            AMADEUS_FLIGHTS_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "originLocationCode": origin_code.upper(),
                "destinationLocationCode": destination_code.upper(),
                "departureDate": departure_date,
                "adults": 1,
                "max": 3,
            },
            timeout=15,
        )
        if resp.ok:
            data = resp.json().get("data", [])
            return data, None, resp.status_code
        err = get_safe_api_error(resp)
        return [], f"Amadeus Flight API error: {err}", resp.status_code
    except requests.exceptions.ConnectionError:
        return [], "The Amadeus sandbox service could not be reached from the current network environment.", None
    except requests.exceptions.Timeout:
        return [], "Amadeus flight search request timed out.", None
    except requests.exceptions.RequestException as e:
        return [], f"Network request error: {str(e)}", None


class ActionSearchFlights(Action):
    """
    Search flight offers via Amadeus sandbox API; fall back to local demonstration dataset.
    Reuses existing slots: origin, destination, travel_dates.
    """

    def name(self) -> Text:
        return "action_search_flights"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        origin_slot = tracker.get_slot("origin") or "London"
        dest_slot = tracker.get_slot("destination") or "Paris"
        dates_slot = tracker.get_slot("travel_dates") or "2026-10-15"

        origin_iata, origin_err = resolve_iata_code(origin_slot)
        dest_iata, dest_err = resolve_iata_code(dest_slot)
        dep_date, date_err = parse_departure_date(dates_slot)

        if origin_err or dest_err or date_err:
            prompt_msg = origin_err or dest_err or date_err
            dispatcher.utter_message(text=f"⚠️ Flight search requirement: {prompt_msg}")
            return [SlotSet("fallback_count", 0)]

        token = get_amadeus_token()
        flights = []
        source_label = ""
        error_msg = None

        if token:
            flights, error_msg, status = search_amadeus_flights(
                origin_iata, dest_iata, dep_date, token
            )
            if flights:
                source_label = "📡 Live data: Amadeus Sandbox Flight Offers API v2"

        lines = [f"✈️ Flight Search: {origin_slot} ({origin_iata}) → {dest_slot} ({dest_iata})\n"]

        if flights:
            lines.append(source_label + "\n")
            for idx, offer in enumerate(flights[:3], start=1):
                price = offer.get("price", {}).get("total", "N/A")
                currency = offer.get("price", {}).get("currency", "EUR")
                itineraries = offer.get("itineraries", [])
                duration = itineraries[0].get("duration", "N/A") if itineraries else "N/A"
                segments = itineraries[0].get("segments", []) if itineraries else []
                carrier = segments[0].get("carrierCode", "Airline") if segments else "Airline"
                flight_num = f"{carrier} {segments[0].get('number', '')}" if segments else carrier
                lines += [
                    f"  {idx}. {flight_num} ({origin_iata} → {dest_iata})",
                    f"     💰 Price: {price} {currency}",
                    f"     ⏱️  Duration: {duration}",
                    f"     🌱 Environmental note: Direct flights generally avoid additional take-off and landing cycles, but no live carbon estimate is available for this offer.",
                    "",
                ]
            lines.append(
                "For actual booking decisions, current schedule, fare, and environmental data must be confirmed directly with the provider."
            )
        else:
            reason = (
                f"Reason: {error_msg}" if error_msg else
                "Reason: Amadeus credentials not configured." if not (AMADEUS_API_KEY and AMADEUS_API_SECRET) else
                "The Amadeus sandbox service could not be reached from the current network environment."
            )
            lines += [
                "⚠️ LOCAL DEMONSTRATION DATA – not live flight availability.\n",
                f"{reason}\n",
                "The records below demonstrate how live offers would be displayed when the API is available. "
                "They do not represent current airline schedules, fares, availability, or verified environmental performance.\n",
            ]
            
            local_data = load_json_file(FALLBACK_FLIGHTS_PATH) or []
            for idx, item in enumerate(local_data[:3], start=1):
                lines += [
                    f"  {idx}. {item.get('title', 'Demonstration Flight Option')}",
                    f"     Route: {origin_iata} → {dest_iata} ({item.get('route', 'Demonstration route')})",
                    f"     Type: {item.get('flight_type', 'Direct')}",
                    f"     Price: {item.get('price', 'Not available from live API')}",
                    f"     Sustainability information: {item.get('sustainability_info', 'Not verified')}",
                    "",
                ]
            lines.append(
                "For actual booking decisions, current schedule, fare and environmental data must be obtained from the live provider."
            )

        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("fallback_count", 0)]


# -----------------------------------------------------------------
# TRIP PLANNING FORM SUBMISSION
# -----------------------------------------------------------------

class ActionSubmitTripPlan(Action):
    """Display trip summary and offer next-step quick replies."""

    def name(self) -> Text:
        return "action_submit_trip_plan"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        destination = tracker.get_slot("destination") or "Not specified"
        travel_dates = tracker.get_slot("travel_dates") or "Not specified"
        budget = tracker.get_slot("budget") or "Not specified"
        sustainability = tracker.get_slot("sustainability_level") or "medium"
        sustainability = normalise_sustainability(sustainability)

        message = (
            "✅ Great! Here is your trip summary:\n\n"
            f"📍 Destination: {destination}\n"
            f"📅 Travel dates: {travel_dates}\n"
            f"💰 Budget: {budget}\n"
            f"♻️ Sustainability preference: {sustainability.upper()}\n\n"
            "What would you like me to help with next?"
        )

        buttons = [
            {"title": "🚆 Sustainable Transport", "payload": "/ask_transport"},
            {"title": "🏨 Eco Accommodation",     "payload": "/ask_accommodation"},
            {"title": "🌿 Sustainable Activities", "payload": "/ask_activities"},
            {"title": "🌍 Carbon Footprint",       "payload": "/ask_carbon"},
            {"title": "👤 Human Advisor",          "payload": "/ask_handover"},
        ]

        dispatcher.utter_message(text=message, buttons=buttons)
        return [
            SlotSet("sustainability_level", sustainability),
            SlotSet("fallback_count", 0),
        ]


# -----------------------------------------------------------------
# SUSTAINABLE TRANSPORT RECOMMENDATION
# -----------------------------------------------------------------

class ActionRecommendTransport(Action):
    """
    Compare rail, car, and air using reference CO2e values.
    Highlight the lower-emission option.
    """

    def name(self) -> Text:
        return "action_recommend_transport"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        destination = tracker.get_slot("destination") or "your destination"
        origin = tracker.get_slot("origin") or "your origin"
        sustainability = normalise_sustainability(
            tracker.get_slot("sustainability_level")
        )

        # Build comparative table using reference values per 100 km
        ref_distance_km = 500  # representative medium journey

        lines = [
            f"🚆 Sustainable Transport Comparison for {origin} → {destination}\n",
            "⚠️ Demonstration/reference estimates — not live Climatiq data (based on UK DEFRA 2023 conversion factors).",
            "For live calculations, the Carbon Footprint feature connects directly to Climatiq.\n",
            f"{'Mode':<10} {'Est. CO₂e (500 km)':<22} {'Indicator'}",
            "-" * 52,
        ]

        modes_sorted = sorted(
            TRANSPORT_CO2E_PER_KM.items(),
            key=lambda kv: kv[1],
        )
        for mode, rate in modes_sorted:
            co2e = rate * ref_distance_km
            label = emissions_label(co2e)
            mode_name = mode.upper()
            lines.append(f"{mode_name:<10} {co2e:.1f} kg CO₂e          {label}")

        lines += [
            "",
            "✅ Rail is typically the lowest-carbon option for medium distances.",
            "🚗 Car depends heavily on occupancy — shared journeys reduce impact.",
            "✈️  Air travel has the highest per-passenger emissions.",
            "",
            f"Your sustainability preference: {sustainability.upper()}",
            "",
            "Ranking based on your preference gives greater weight to "
            + ("lower emissions." if sustainability == "high" else
               "a balance of price and emissions." if sustainability == "medium"
               else "price and convenience."),
            "",
            "Note: These are indicative comparative values only, not precise "
            "measurements for your specific journey.",
        ]

        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("fallback_count", 0)]


# -----------------------------------------------------------------
# ECO ACCOMMODATION RECOMMENDATION
# -----------------------------------------------------------------

class ActionRecommendAccommodation(Action):
    """
    Retrieve hotels via Amadeus sandbox; fall back to local dataset.
    Rank results using weighted scoring based on sustainability preference.
    """

    def name(self) -> Text:
        return "action_recommend_accommodation"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        destination = tracker.get_slot("destination") or ""
        budget_raw = tracker.get_slot("budget") or ""
        sustainability = normalise_sustainability(
            tracker.get_slot("sustainability_level")
        )

        # Attempt Amadeus live search
        hotels: List[Dict] = []
        source_label = ""
        live_attempted = False

        token = get_amadeus_token()
        if token and destination:
            live_attempted = True
            # Use first word as city code approximation (IATA 3-letter codes needed)
            city_guess = destination.strip().upper()[:3]
            raw_hotels = search_amadeus_hotels(city_guess, token)
            if raw_hotels:
                for h in raw_hotels[:6]:
                    hotels.append({
                        "name": h.get("name", "Unknown Hotel"),
                        "destination": destination,
                        "price": 120,  # Amadeus sandbox rarely returns prices
                        "carbon_score": 6,
                        "sustainability_score": 5,
                        "features": "Retrieved from Amadeus sandbox. "
                                    "Environmental features not verified.",
                        "source": "Amadeus Sandbox API",
                        "verified": False,
                    })
                source_label = "📡 Live data: Amadeus Sandbox API"

        # Fall back to local dataset if live failed or returned nothing
        if not hotels:
            local_data = load_json_file(FALLBACK_HOTELS_PATH) or []
            dest_lower = destination.lower()
            hotels = [
                h for h in local_data
                if dest_lower in h.get("destination", "").lower()
            ]
            if not hotels:
                # Return all fallback entries when destination not matched
                hotels = local_data[:5] if local_data else []
            source_label = (
                "⚠️ LOCAL DEMONSTRATION DATA – not live hotel availability.\n"
                + ("  (Amadeus credentials not configured.)"
                   if not (AMADEUS_API_KEY and AMADEUS_API_SECRET)
                   else "  (Amadeus API returned no results for this destination.)")
            )

        if not hotels:
            dispatcher.utter_message(
                text=(
                    "I was unable to find accommodation data for "
                    f"{destination or 'your destination'} at this time. "
                    "Please try a different destination or check back later."
                )
            )
            return [SlotSet("fallback_count", 0)]

        ranked = rank_hotels(hotels, sustainability)
        weights = ranking_weights(sustainability)
        weight_desc = (
            f"carbon {int(weights['carbon']*100)}% / "
            f"price {int(weights['price']*100)}% / "
            f"eco-quality {int(weights['quality']*100)}%"
        )

        lines = [
            f"🏨 Eco Accommodation Recommendations for {destination or 'your destination'}\n",
            source_label,
            "",
            f"Ranked using your {sustainability.upper()} sustainability preference "
            f"({weight_desc}).\n",
        ]

        for idx, hotel in enumerate(ranked[:4], start=1):
            price_str = f"~£{hotel.get('price', '?')}/night"
            cs = hotel.get("carbon_score", "?")
            qs = hotel.get("sustainability_score", "?")
            lines += [
                f"  {idx}. {hotel.get('name', 'Hotel')}",
                f"     💰 Price: {price_str}",
                f"     🌱 Carbon score: {cs}/10",
                f"     ♻️  Eco score: {qs}/10",
                f"     📝 {hotel.get('features', '')}",
                f"     🔗 Source: {hotel.get('source', 'Local data')}",
                "",
            ]

        lines.append(
            "⚠️ Sustainability claims are based on information reported by the source "
            "and have not been independently verified. Always confirm directly with "
            "the accommodation provider."
        )

        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("fallback_count", 0)]


# -----------------------------------------------------------------
# SUSTAINABLE ACTIVITIES
# -----------------------------------------------------------------

class ActionRecommendActivities(Action):
    """Provide destination-aware sustainable activity suggestions."""

    def name(self) -> Text:
        return "action_recommend_activities"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        destination = tracker.get_slot("destination") or "your destination"
        dest_lower = destination.lower()

        # Load local activity data
        local_data = load_json_file(FALLBACK_ACTIVITIES_PATH) or {}

        # Try to match destination-specific suggestions
        activities: List[str] = []
        for key in local_data:
            if key.lower() in dest_lower or dest_lower in key.lower():
                activities = local_data[key]
                break

        # Generic sustainable activities as fallback
        if not activities:
            activities = local_data.get("_generic", [
                "🚶 Walking tours of the historic city centre",
                "🚲 Cycling to local markets and parks",
                "🎭 Attend a local cultural performance or festival",
                "🌿 Visit a community-run nature reserve or eco-park",
                "🛍️ Shop at local artisan markets supporting local producers",
                "🚌 Use public transport for all local journeys",
                "🍽️ Eat at locally owned restaurants using seasonal ingredients",
                "🏛️ Visit community museums and heritage sites",
            ])

        lines = [
            f"🌿 Sustainable Activity Suggestions for {destination}\n",
            "These suggestions prioritise low-impact, community-based, "
            "and culturally meaningful experiences:\n",
        ]
        for activity in activities:
            lines.append(f"  • {activity}")

        lines += [
            "",
            "⚠️ These are general destination-based suggestions. "
            "Sustainability credentials listed are as reported by operators "
            "and have not been independently certified.",
            "",
            "Always research individual operators for the most current "
            "environmental policies.",
        ]

        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("fallback_count", 0)]


# -----------------------------------------------------------------
# CLIMATIQ CARBON FOOTPRINT CALCULATOR
# -----------------------------------------------------------------

class ActionCalculateCarbon(Action):
    """
    Calculate travel emissions using the Climatiq Travel API.
    Handles full error recovery and always returns a meaningful response.
    API key is read from environment variables – never logged or exposed.
    """

    def name(self) -> Text:
        return "action_calculate_carbon"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        origin = (tracker.get_slot("origin") or "").strip()
        destination = (tracker.get_slot("destination") or "").strip()
        raw_mode = (tracker.get_slot("transport_mode") or "").strip()
        transport_mode = normalise_transport_mode(raw_mode)

        # ── Validate required fields ─────────────────────────────
        if not origin or not destination or not transport_mode:
            dispatcher.utter_message(
                text=(
                    "I need your origin, destination, and transport mode "
                    "to calculate the carbon footprint. "
                    "Please provide all three details."
                )
            )
            return [SlotSet("fallback_count", 0)]

        if transport_mode not in ("rail", "car", "air"):
            dispatcher.utter_message(
                text=(
                    f"I don't recognise '{raw_mode}' as a transport mode. "
                    "I can calculate emissions for rail, car, or air. "
                    "Please enter one of those options."
                )
            )
            return [SlotSet("fallback_count", 0)]

        # ── Check API key ────────────────────────────────────────
        if not CLIMATIQ_API_KEY:
            dispatcher.utter_message(
                text=(
                    "The carbon calculation service is temporarily unavailable "
                    "because the Climatiq API key is not configured. "
                    "Please contact the administrator."
                )
            )
            return [SlotSet("fallback_count", 0)]

        # ── Build Climatiq request ───────────────────────────────
        # Official Climatiq Travel API v1 (GA) schema:
        # POST https://api.climatiq.io/travel/v1/distance
        # Request fields per official GA documentation:
        #   origin       : { "query": "<city name>" }
        #   destination  : { "query": "<city name>" }
        #   travel_mode  : "air" | "car" | "rail"
        # Source: https://www.climatiq.io/docs/api-reference/travel/travel-v1
        headers = {
            "Authorization": f"Bearer {CLIMATIQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "origin": {"query": origin},
            "destination": {"query": destination},
            "travel_mode": transport_mode,
        }

        start_time = time.monotonic()

        try:
            response = requests.post(
                CLIMATIQ_TRAVEL_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
            latency_ms = int((time.monotonic() - start_time) * 1000)

            # ── Auth / access errors ─────────────────────────────
            if response.status_code == 401:
                dispatcher.utter_message(
                    text=(
                        "The carbon calculation service could not authenticate. "
                        "Please verify the Climatiq API key configuration."
                    )
                )
                return [SlotSet("fallback_count", 0)]

            if response.status_code == 403:
                # Distinguish between invalid key and premium plan restriction
                try:
                    err_body = response.json()
                    err_msg = err_body.get("message", "")
                except (ValueError, KeyError):
                    err_msg = ""

                if "premium" in err_msg.lower() or "upgrade" in err_msg.lower():
                    dispatcher.utter_message(
                        text=(
                            "The Climatiq Travel API requires a paid plan. "
                            "The current API key subscription does not include access "
                            "to the Travel emissions endpoint.\n\n"
                            "To enable live carbon calculations, the Climatiq account "
                            "must be upgraded to a plan that includes Travel API access "
                            "(https://www.climatiq.io).\n\n"
                            "The system is otherwise configured correctly with the "
                            "correct endpoint and field names per the official "
                            "Travel V1 GA documentation."
                        )
                    )
                else:
                    dispatcher.utter_message(
                        text=(
                            "Access to the Climatiq carbon calculation service was denied. "
                            "Please verify the API key configuration."
                        )
                    )
                return [SlotSet("fallback_count", 0)]

            # ── Rate limiting ────────────────────────────────────
            if response.status_code == 429:
                dispatcher.utter_message(
                    text=(
                        "The carbon calculation service is temporarily rate-limited. "
                        "Please try again in a few moments."
                    )
                )
                return [SlotSet("fallback_count", 0)]

            # ── Server errors ────────────────────────────────────
            if response.status_code >= 500:
                dispatcher.utter_message(
                    text=(
                        "The Climatiq service is temporarily unavailable (server error). "
                        "Please try again shortly."
                    )
                )
                return [SlotSet("fallback_count", 0)]

            # ── Other HTTP errors ────────────────────────────────
            if not response.ok:
                safe_error = get_safe_api_error(response)
                dispatcher.utter_message(
                    text=(
                        "I couldn't complete the carbon calculation.\n\n"
                        f"Service response: {safe_error}\n\n"
                        "Please check that the origin and destination cities are "
                        "recognised locations and try again."
                    )
                )
                return [SlotSet("fallback_count", 0)]

            # ── Parse successful response ────────────────────────
            try:
                data = response.json()
            except ValueError:
                dispatcher.utter_message(
                    text=(
                        "The carbon service returned an unreadable response. "
                        "Please try again later."
                    )
                )
                return [SlotSet("fallback_count", 0)]

            co2e = data.get("co2e")
            co2e_unit = data.get("co2e_unit", "kg")
            distance_km = data.get("distance_km")
            calc_method = data.get("co2e_calculation_method", "Not specified")

            # Extract resolved location names from response if provided
            api_origin = (
                data.get("origin", {}).get("name", origin)
                if isinstance(data.get("origin"), dict) else origin
            )
            api_destination = (
                data.get("destination", {}).get("name", destination)
                if isinstance(data.get("destination"), dict) else destination
            )

            if co2e is None:
                dispatcher.utter_message(
                    text=(
                        "Climatiq responded successfully, but did not return "
                        "an emissions estimate for this journey. "
                        "Please try a different route or transport mode."
                    )
                )
                return [SlotSet("fallback_count", 0)]

            try:
                co2e_float = float(co2e)
                co2e_display = f"{co2e_float:.2f}"
            except (TypeError, ValueError):
                co2e_float = 0.0
                co2e_display = str(co2e)

            if distance_km is not None:
                try:
                    dist_display = f"{float(distance_km):.1f} km"
                except (TypeError, ValueError):
                    dist_display = f"{distance_km} km"
            else:
                dist_display = "Not available"

            label = emissions_label(co2e_float)

            message = (
                "🌍 LIVE CARBON FOOTPRINT ESTIMATE\n"
                "(Source: Climatiq Emissions API)\n\n"
                f"📍 Origin:            {api_origin}\n"
                f"📍 Destination:       {api_destination}\n"
                f"🚆 Transport mode:    {transport_mode.upper()}\n"
                f"📏 Journey distance:  {dist_display}\n"
                f"🌱 Estimated CO₂e:   {co2e_display} {co2e_unit}\n"
                f"📊 Emissions level:   {label}\n"
                f"🧮 Calculation method: {calc_method}\n"
                f"⏱️  API response time: {latency_ms} ms\n\n"
                "This estimate is for one-way travel for one passenger. "
                "Return journeys and additional passengers must be calculated separately.\n\n"
                "⚠️ Carbon estimates are indicative figures derived from an "
                "external emissions-data provider (Climatiq) and are not guaranteed "
                "exact measurements."
            )

            dispatcher.utter_message(text=message)
            return [
                SlotSet("transport_mode", transport_mode),
                SlotSet("fallback_count", 0),
            ]

        except requests.exceptions.Timeout:
            dispatcher.utter_message(
                text=(
                    "The Climatiq request timed out after 20 seconds. "
                    "Please check your internet connection and try again."
                )
            )

        except requests.exceptions.ConnectionError:
            dispatcher.utter_message(
                text=(
                    "I could not connect to the Climatiq service. "
                    "Please check your internet connection and try again."
                )
            )

        except requests.exceptions.RequestException:
            dispatcher.utter_message(
                text=(
                    "An unexpected network error occurred while contacting Climatiq. "
                    "Please try again later."
                )
            )

        return [SlotSet("fallback_count", 0)]


# -----------------------------------------------------------------
# HUMAN HANDOVER
# -----------------------------------------------------------------

class ActionHumanHandover(Action):
    """
    Prepare a full conversation context package for a human travel advisor.
    This is a demonstration of escalation – no live agent platform is connected.
    """

    def name(self) -> Text:
        return "action_human_handover"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        sender_id = tracker.sender_id
        destination = tracker.get_slot("destination")
        travel_dates = tracker.get_slot("travel_dates")
        budget = tracker.get_slot("budget")
        sustainability = tracker.get_slot("sustainability_level")
        origin = tracker.get_slot("origin")
        transport_mode = tracker.get_slot("transport_mode")
        latest_message = tracker.latest_message.get("text", "")

        # Build conversation history from tracker events
        conversation_lines: List[str] = []
        for event in tracker.events:
            event_type = event.get("event")
            if event_type == "user":
                text = event.get("text", "")
                if text and not text.startswith("/"):
                    conversation_lines.append(f"  User: {text}")
            elif event_type == "bot":
                text = event.get("text", "")
                if text:
                    # Truncate very long bot messages in the handover log
                    preview = text[:200] + "..." if len(text) > 200 else text
                    conversation_lines.append(f"  Bot:  {preview}")

        history = (
            "\n".join(conversation_lines)
            if conversation_lines
            else "  No conversation history available."
        )

        context = (
            "👤 HUMAN ADVISOR HANDOVER PACKAGE\n"
            "══════════════════════════════════\n\n"
            f"Conversation ID: {sender_id}\n\n"
            "── TRIP CONTEXT ──────────────────\n"
            f"  Origin:                  {origin or 'Not provided'}\n"
            f"  Destination:             {destination or 'Not provided'}\n"
            f"  Travel dates:            {travel_dates or 'Not provided'}\n"
            f"  Budget:                  {budget or 'Not provided'}\n"
            f"  Sustainability preference: {sustainability or 'Not provided'}\n"
            f"  Transport mode:          {transport_mode or 'Not provided'}\n"
            f"  Latest user message:     {latest_message}\n\n"
            "── CONVERSATION HISTORY ───────────\n"
            f"{history}\n\n"
            "══════════════════════════════════\n"
            "Your conversation context has been prepared for a human travel advisor.\n"
            "A specialist will review your request and respond as soon as possible.\n\n"
            "⚠️ Note: This is a demonstration of the escalation feature. "
            "In a production deployment, this context package would be transmitted "
            "to a live agent platform."
        )

        dispatcher.utter_message(text=context)
        return [
            SlotSet("fallback_count", 0),
            FollowupAction("action_listen"),
        ]


# -----------------------------------------------------------------
# VERIFIED CARBON OFFSET PROGRAMMES & STANDARDS RECOMMENDATION
# -----------------------------------------------------------------

class ActionRecommendCarbonOffsets(Action):
    """
    Provide factual information on verified carbon-offset standards, registries,
    and governance frameworks. Strictly emphasizes the mitigation hierarchy:
    Avoid -> Reduce -> Lower-carbon options -> Residual offset consideration.
    Prevents greenwashing by avoiding claims of automatic carbon neutrality.
    """

    def name(self) -> Text:
        return "action_recommend_carbon_offsets"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        programs_data = load_json_file(CARBON_OFFSET_PROGRAMS_PATH)

        if not programs_data or not isinstance(programs_data, list):
            dispatcher.utter_message(
                text=(
                    "I can't load the verified carbon-offset resource list right now. "
                    "Reducing emissions directly remains the preferred first step."
                )
            )
            return [SlotSet("fallback_count", 0)]

        lines = [
            "🌱 Verified Carbon Offset Standards & Governance Resources\n",
            "⚠️ Mitigation Hierarchy Guidance:",
            "Reducing travel emissions should come first. Where emissions cannot reasonably be avoided or reduced, verified carbon-credit programmes may be considered for residual emissions.\n",
            "Purchasing carbon credits does not make high-emission travel carbon-neutral or zero-emission by itself. Below are independent standards and registries for residual emissions context:\n",
        ]

        for idx, item in enumerate(programs_data, start=1):
            lines += [
                f"{idx}. {item.get('name', 'Unverified Standard')}",
                f"   • Organisation: {item.get('organisation', 'Independent Body')}",
                f"   • Type: {item.get('type', 'Standard / Registry')}",
                f"   • Standard / Framework: {item.get('verification_or_standard', 'Specified Standard')}",
                f"   • Overview: {item.get('description', 'No description available.')}",
                f"   • Official Source: {item.get('official_url', 'N/A')}",
                "",
            ]

        lines.append(
            "Carbon credits should complement, not replace, direct emissions reductions. "
            "Check the programme's current methodology, registry information and project documentation before making a purchase."
        )

        dispatcher.utter_message(text="\n".join(lines))
        return [SlotSet("fallback_count", 0)]


# -----------------------------------------------------------------
# TWO-STAGE FALLBACK
# -----------------------------------------------------------------

class ActionHandleFallback(Action):
    """
    Stage 1 (fallback_count < 1): Show clarification menu with quick-reply buttons.
    Stage 2 (fallback_count >= 1): Escalate to human handover.
    """

    def name(self) -> Text:
        return "action_handle_fallback"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        try:
            fallback_count = float(tracker.get_slot("fallback_count") or 0)
        except (TypeError, ValueError):
            fallback_count = 0.0

        if fallback_count < 1:
            dispatcher.utter_message(
                text=(
                    "I'm sorry, I couldn't confidently understand your request. "
                    "Please choose one of the options below, or try rephrasing "
                    "your message."
                ),
                buttons=[
                    {"title": "🌍 Plan a Trip",          "payload": "/plan_trip"},
                    {"title": "🚆 Sustainable Transport", "payload": "/ask_transport"},
                    {"title": "🏨 Eco Accommodation",     "payload": "/ask_accommodation"},
                    {"title": "🌿 Sustainable Activities","payload": "/ask_activities"},
                    {"title": "🌍 Carbon Footprint",      "payload": "/ask_carbon"},
                    {"title": "👤 Human Advisor",         "payload": "/ask_handover"},
                ],
            )
            return [SlotSet("fallback_count", 1)]

        # Stage 2 – escalate to human advisor
        dispatcher.utter_message(
            text=(
                "I'm still unable to confidently understand your request. "
                "To avoid giving you incorrect travel advice, I am escalating "
                "your conversation to a human travel advisor."
            )
        )
        return [
            SlotSet("fallback_count", 0),
            FollowupAction("action_human_handover"),
        ]