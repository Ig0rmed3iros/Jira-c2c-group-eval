from jql import find_group_references

NAME = "jira-users"
GID = "8bec6c67-2893-4e55-a124-16c250107f33"


def test_members_of_quoted():
    hits = find_group_references('assignee in membersOf("jira-users")', NAME, GID)
    assert hits == ['membersOf("jira-users")']


def test_members_of_unquoted():
    hits = find_group_references("reporter in membersOf(jira-users)", NAME, GID)
    assert hits == ["membersOf(jira-users)"]


def test_members_of_by_group_id():
    jql = f'watcher in membersOf("{GID}")'
    hits = find_group_references(jql, NAME, GID)
    assert hits == [f'membersOf("{GID}")']


def test_group_equals():
    hits = find_group_references('group = "jira-users" AND status = Open', NAME, GID)
    assert hits == ['group = "jira-users"']


def test_group_in_list():
    hits = find_group_references('group in ("admins", "jira-users")', NAME, GID)
    assert hits == ['group in ("admins", "jira-users")']


def test_case_insensitive_name():
    hits = find_group_references('membersOf("JIRA-USERS")', NAME, GID)
    assert hits == ['membersOf("JIRA-USERS")']


def test_no_match_for_other_group():
    assert find_group_references('membersOf("administrators")', NAME, GID) == []


def test_false_positive_project_key_guard():
    # a project/text that merely contains the group name must NOT match
    jql = 'project = "JIRA-USERS-PORTAL" AND text ~ "jira-users guide"'
    assert find_group_references(jql, NAME, GID) == []


def test_multiple_refs_deduped_in_order():
    jql = 'membersOf("jira-users") OR group = "jira-users"'
    hits = find_group_references(jql, NAME, GID)
    assert hits == ['membersOf("jira-users")', 'group = "jira-users"']


def test_group_not_equals():
    hits = find_group_references('group != "jira-users"', NAME, GID)
    assert hits == ['group != "jira-users"']


def test_group_not_in():
    hits = find_group_references('group not in ("jira-users")', NAME, GID)
    assert hits == ['group not in ("jira-users")']
