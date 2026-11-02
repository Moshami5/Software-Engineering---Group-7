"""Unit tests for FR-2 (study context) and NFR-3 (missing values labelled).

Test data: values typed by hand, chosen on and just outside the SRS limits
(hours 1-40, weeks 1-52), plus empty, blank and NaN inputs.
"""
import math

import pytest

from src.study_context import (COURSES_MESSAGE, HOURS_MESSAGE, LANGUAGE_MESSAGE,
                               MAX_HOURS_PER_WEEK, MAX_WEEKS_AVAILABLE,
                               MIN_HOURS_PER_WEEK, MIN_WEEKS_AVAILABLE, NOT_GIVEN,
                               NOT_LISTED, WEEKS_MESSAGE, StudyContext,
                               label_missing, validate_study_context)

# --- FR-2: valid input is stored, cleaned ------------------------------------
def test_valid_context_is_stored():
    result = validate_study_context("English", 8, 12, ["Intro to Python", "SQL Basics"])
    assert result.ok and result.error == ""
    assert result.value == StudyContext("English", 8.0, 12.0,
                                        ("Intro to Python", "SQL Basics"))

def test_text_input_is_trimmed_and_numbers_typed_as_text_are_accepted():
    result = validate_study_context("  English ", " 8 ", "12")
    assert result.ok
    assert (result.value.language, result.value.hours_per_week,
            result.value.weeks_available) == ("English", 8.0, 12.0)

# --- FR-2: limits (boundary values) ------------------------------------------
@pytest.mark.parametrize("hours", [MIN_HOURS_PER_WEEK, MAX_HOURS_PER_WEEK, 7.5])
def test_hours_inside_limits_are_accepted(hours):
    result = validate_study_context(hours_per_week=hours)
    assert result.ok and result.value.hours_per_week == hours


@pytest.mark.parametrize("hours", [0, 0.5, 41, -3, "lots", True])
def test_hours_outside_limits_are_refused_with_message(hours):
    result = validate_study_context(hours_per_week=hours)
    assert not result.ok
    assert result.value is None
    assert result.error == HOURS_MESSAGE == "Hours per week must be a number from 1 to 40"


@pytest.mark.parametrize("weeks", [MIN_WEEKS_AVAILABLE, MAX_WEEKS_AVAILABLE])
def test_weeks_on_the_limits_are_accepted(weeks):
    assert validate_study_context(weeks_available=weeks).value.weeks_available == weeks


@pytest.mark.parametrize("weeks", [0, 53, "soon"])
def test_weeks_outside_limits_are_refused_with_message(weeks):
    result = validate_study_context(weeks_available=weeks)
    assert not result.ok
    assert result.error == WEEKS_MESSAGE == "Weeks available must be a number from 1 to 52"


def test_language_that_is_not_text_is_refused():
    result = validate_study_context(language=42)
    assert not result.ok and result.error == LANGUAGE_MESSAGE


# --- FR-2: missing fields are "not given" and their checks are skipped --------
def test_nothing_given_shows_not_given_everywhere():
    ctx = validate_study_context().value
    assert ctx.display() == {"language": NOT_GIVEN, "hours_per_week": NOT_GIVEN,
                             "weeks_available": NOT_GIVEN, "completed_courses": NOT_GIVEN}
    assert len(ctx.missing_fields()) == 4


@pytest.mark.parametrize("empty", [None, "", "   ", float("nan")])
def test_blank_and_nan_count_as_not_given(empty):
    result = validate_study_context(language=empty, hours_per_week=empty,
                                    weeks_available=empty, completed_courses=empty)
    assert result.ok
    assert result.value.missing_fields() == ["language", "hours_per_week",
                                             "weeks_available", "completed_courses"]


def test_only_the_missing_field_is_skipped():
    ctx = validate_study_context(language="English", weeks_available=10).value
    assert ctx.is_given("language") and ctx.is_given("weeks_available")
    assert not ctx.is_given("hours_per_week")       # FR-5 skips the hours check
    assert ctx.display()["hours_per_week"] == NOT_GIVEN
    assert ctx.display()["language"] == "English"


def test_unknown_field_name_is_an_error():
    with pytest.raises(KeyError):
        validate_study_context().value.is_given("favourite_colour")


# --- FR-2: completed courses are cleaned ------------------------------------
def test_completed_courses_are_trimmed_and_deduplicated():
    result = validate_study_context(completed_courses=[" Intro to Python ", "",
                                                       "intro to python", None, "SQL Basics"])
    assert result.value.completed_courses == ("Intro to Python", "SQL Basics")


def test_completed_courses_from_a_text_box_are_split_on_commas():
    result = validate_study_context(completed_courses="Intro to Python, SQL Basics,")
    assert result.value.completed_courses == ("Intro to Python", "SQL Basics")


@pytest.mark.parametrize("bad", [42, ["Intro to Python", 7]])
def test_completed_courses_that_are_not_titles_are_refused(bad):
    result = validate_study_context(completed_courses=bad)
    assert not result.ok and result.error == COURSES_MESSAGE


# --- NFR-3: missing course data is labelled, not a crash ---------------------
@pytest.mark.parametrize("missing", [None, "", "  ", float("nan")])
def test_missing_course_value_is_labelled_not_listed(missing):
    assert label_missing(missing) == NOT_LISTED


@pytest.mark.parametrize("value", [4.0, 0, "English"])
def test_real_course_value_is_returned_unchanged(value):
    assert label_missing(value) == value


def test_label_can_be_changed_to_unknown():
    assert label_missing(math.nan, label="unknown") == "unknown"