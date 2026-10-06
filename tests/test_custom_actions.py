"""
Unit tests for EcoTravel Advisor Custom Actions
"""

import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.actions import (
    ActionSubmitTripPlan,
    ActionGenerateItinerary,
    ActionRecommendDining,
    ActionRecommendPacking,
    ActionProvideEcoTips,
    ActionBudgetBreakdown,
    ActionWeatherAdvice,
    ActionRecommendTransport,
    ActionRecommendAccommodation,
    ActionRecommendActivities,
    ActionRecommendCarbonOffsets,
    ActionHumanHandover,
    ActionHandleFallback,
    parse_days_count,
    normalise_sustainability,
    normalise_transport_mode,
)


class TestHelpers(unittest.TestCase):
    def test_parse_days_count(self):
        self.assertEqual(parse_days_count("3 days"), 3)
        self.assertEqual(parse_days_count("5 days"), 5)
        self.assertEqual(parse_days_count("1 week"), 7)
        self.assertEqual(parse_days_count("2 weeks"), 14)
        self.assertEqual(parse_days_count("weekend getaway"), 3)
        self.assertEqual(parse_days_count(None), 3)

    def test_normalise_sustainability(self):
        self.assertEqual(normalise_sustainability("high"), "high")
        self.assertEqual(normalise_sustainability("maximum green"), "high")
        self.assertEqual(normalise_sustainability("low"), "low")
        self.assertEqual(normalise_sustainability("medium"), "medium")
        self.assertEqual(normalise_sustainability(None), "medium")

    def test_normalise_transport_mode(self):
        self.assertEqual(normalise_transport_mode("train"), "rail")
        self.assertEqual(normalise_transport_mode("flight"), "air")
        self.assertEqual(normalise_transport_mode("driving"), "car")
        self.assertEqual(normalise_transport_mode("rail"), "rail")


class TestActions(unittest.TestCase):
    def setUp(self):
        self.dispatcher = MagicMock()
        self.tracker = MagicMock()
        self.domain = {}

    def test_submit_trip_plan(self):
        self.tracker.get_slot.side_effect = lambda k: {
            "destination": "Paris",
            "trip_duration": "5 days",
            "travel_dates": "10-15 Oct",
            "travel_party": "Couple",
            "trip_style": "Nature & Wildlife",
            "travel_pace": "Balanced",
            "budget": "1000 euros",
            "sustainability_level": "high",
        }.get(k)

        action = ActionSubmitTripPlan()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("MASTER SUSTAINABLE TRIP PLAN", call_kwargs["text"])
        self.assertIn("PARIS", call_kwargs["text"])
        self.assertIn("5 full days", call_kwargs["text"])
        self.assertGreater(len(call_kwargs["buttons"]), 3)

    def test_generate_itinerary(self):
        self.tracker.get_slot.side_effect = lambda k: {
            "destination": "Berlin",
            "trip_duration": "3 days",
            "trip_style": "Culture & History",
            "travel_pace": "Relaxed",
        }.get(k)

        action = ActionGenerateItinerary()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("3-DAY SUSTAINABLE ITINERARY", call_kwargs["text"])
        self.assertIn("DAY 1:", call_kwargs["text"])
        self.assertIn("DAY 2:", call_kwargs["text"])
        self.assertIn("DAY 3:", call_kwargs["text"])

    def test_recommend_dining(self):
        self.tracker.get_slot.side_effect = lambda k: {
            "destination": "Paris",
        }.get(k)

        action = ActionRecommendDining()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("DINING: PARIS", call_kwargs["text"])
        self.assertIn("Specialty", call_kwargs["text"])

    def test_recommend_packing(self):
        self.tracker.get_slot.side_effect = lambda k: {
            "destination": "Amsterdam",
            "travel_dates": "July",
        }.get(k)

        action = ActionRecommendPacking()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("ZERO-WASTE ECO-PACKING CHECKLIST", call_kwargs["text"])
        self.assertIn("water bottle", call_kwargs["text"].lower())

    def test_provide_eco_tips(self):
        action = ActionProvideEcoTips()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("ECO-TRAVEL GUIDELINES", call_kwargs["text"])

    def test_budget_breakdown(self):
        self.tracker.get_slot.side_effect = lambda k: {
            "destination": "Rome",
            "trip_duration": "5 days",
            "budget": "1200 euros",
        }.get(k)

        action = ActionBudgetBreakdown()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("SUSTAINABLE BUDGET ALLOCATION", call_kwargs["text"])
        self.assertIn("€1200", call_kwargs["text"])

    def test_weather_advice(self):
        self.tracker.get_slot.side_effect = lambda k: {
            "destination": "Barcelona",
        }.get(k)

        action = ActionWeatherAdvice()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("CLIMATE & ECO-SEASON GUIDE", call_kwargs["text"])

    def test_human_handover(self):
        self.tracker.sender_id = "test_user_123"
        self.tracker.get_slot.side_effect = lambda k: "Test value"
        self.tracker.latest_message = {"text": "I want human help"}
        self.tracker.events = []

        action = ActionHumanHandover()
        events = action.run(self.dispatcher, self.tracker, self.domain)
        self.assertTrue(self.dispatcher.utter_message.called)
        call_kwargs = self.dispatcher.utter_message.call_args[1]
        self.assertIn("HUMAN ADVISOR ESCALATION DOSSIER", call_kwargs["text"])
        self.assertIn("test_user_123", call_kwargs["text"])


if __name__ == "__main__":
    unittest.main()
