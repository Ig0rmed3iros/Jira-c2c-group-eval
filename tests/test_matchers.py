from matchers import holder_matches_group

NAME = "jira-users"
GID = "gid-1"


def test_match_by_parameter_name():
    h = {"type": "group", "parameter": "jira-users"}
    assert holder_matches_group(h, NAME, GID) is True


def test_match_by_value_group_id():
    h = {"type": "group", "value": "gid-1"}
    assert holder_matches_group(h, NAME, GID) is True


def test_match_by_nested_group_object():
    h = {"type": "group", "group": {"name": "jira-users", "groupId": "gid-1"}}
    assert holder_matches_group(h, NAME, GID) is True


def test_match_name_case_insensitive():
    h = {"type": "group", "parameter": "JIRA-USERS"}
    assert holder_matches_group(h, NAME, GID) is True


def test_no_match_other_group():
    h = {"type": "group", "parameter": "administrators", "value": "gid-9"}
    assert holder_matches_group(h, NAME, GID) is False


def test_no_match_non_group_holder():
    h = {"type": "projectRole", "parameter": "10037"}
    assert holder_matches_group(h, NAME, GID) is False
