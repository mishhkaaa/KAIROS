"""The web researcher's search parsing: no network, no browser."""
import base64

from kairos_agents.library.web import result_links, search_query, wiki_results


def test_the_question_is_searched_without_the_request_to_search():
    assert search_query("What is the latest stable version of Python? Search the web.") == "What is the latest stable version of Python"


def test_wikipedia_search_json_becomes_article_urls():
    text = '{"query": {"search": [{"title": "Python (programming language)"}, {"title": "History of Python"}]}}'
    assert wiki_results(text) == ["https://en.wikipedia.org/wiki/Python_(programming_language)",
                                  "https://en.wikipedia.org/wiki/History_of_Python"]
    assert wiki_results("not json") == []


def test_result_links_unwrap_redirects_and_drop_the_engines_own_links():
    wrapped = "a1" + base64.urlsafe_b64encode(b"https://docs.python.org/3/").decode().rstrip("=")
    links = ["https://duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FPython", "https://www.mojeek.com/about",
             f"https://www.bing.com/ck/a?!&&p=x&u={wrapped}", "https://www.python.org/downloads/"]
    assert result_links(links)[:2] == ["https://en.wikipedia.org/wiki/Python", "https://docs.python.org/3/"]
