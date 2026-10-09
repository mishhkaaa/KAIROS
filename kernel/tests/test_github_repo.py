import pytest
from kairos_contracts.errors import KairosError
from kairos_kernel.gateway.connectors import github_repo


@pytest.mark.parametrize("pasted", ["mishhkaaa/KAIROS", "https://github.com/mishhkaaa/KAIROS", "https://github.com/mishhkaaa/KAIROS.git",
                                    "git@github.com:mishhkaaa/KAIROS.git", "github.com/mishhkaaa/KAIROS/tree/main", " mishhkaaa/KAIROS/ "])
def test_github_repo_accepts_what_people_paste(pasted):
    assert github_repo(pasted) == ("mishhkaaa", "KAIROS")


def test_a_bare_repo_name_is_refused_clearly():
    # "KAIROS" alone used to become /repos/KAIROS//issues and a 404 from GitHub at sync time
    with pytest.raises(KairosError, match="owner/repo"):
        github_repo("KAIROS")
