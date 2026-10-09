"""OllamaProvider against a stubbed HTTP transport (no Ollama needed)."""
import asyncio
import json

import httpx
import pytest
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import EmbedRequest
from kairos_models.providers.ollama import OllamaProvider


def provider(handler) -> tuple[OllamaProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    p = OllamaProvider("http://ollama")
    p.client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(record))
    return p, seen


def test_embed_sends_one_batch_request():
    def handler(request):
        texts = json.loads(request.content)["input"]
        return httpx.Response(200, json={"embeddings": [[float(len(t)), 1.0] for t in texts]})

    p, seen = provider(handler)
    res = asyncio.run(p.embed(EmbedRequest(texts=["a", "bb", "ccc"]), "nomic-embed-text"))
    assert [r.url.path for r in seen] == ["/api/embed"]
    assert res.dim == 2 and [v[0] for v in res.vectors] == [1.0, 2.0, 3.0]


def test_embed_of_nothing_makes_no_request():
    p, seen = provider(lambda r: httpx.Response(500))
    res = asyncio.run(p.embed(EmbedRequest(texts=[]), "nomic-embed-text"))
    assert res.vectors == [] and seen == []


@pytest.mark.parametrize("response", [httpx.Response(404, text="model not found"), httpx.Response(200, json={"embeddings": [[1.0]]})])
def test_embed_errors_are_model_unavailable(response):
    p, _ = provider(lambda r: response)
    with pytest.raises(KairosError) as e:
        asyncio.run(p.embed(EmbedRequest(texts=["a", "b"]), "nomic-embed-text"))
    assert e.value.code == "MODEL_UNAVAILABLE"


def _raise(exc):
    def handler(request):
        raise exc

    return handler


def test_an_unreachable_ollama_says_so():
    """An Ollama restart used to fail agents with "ollama qwen2.5:7b-instruct: " and nothing after it."""
    from kairos_contracts.schema import ChatMessage, ModelRequest, Role

    req = ModelRequest(messages=[ChatMessage(role=Role.USER, content="hi")])
    p, _ = provider(_raise(httpx.ConnectError("")))
    with pytest.raises(KairosError) as e:
        asyncio.run(p.generate(req, "qwen2.5:7b-instruct"))
    assert e.value.code == "MODEL_UNAVAILABLE"
    assert e.value.message == "ollama qwen2.5:7b-instruct: cannot reach Ollama at http://ollama (ConnectError)"

    p, _ = provider(_raise(httpx.ConnectError("")))
    with pytest.raises(KairosError) as e:
        asyncio.run(p.embed(EmbedRequest(texts=["a"]), "nomic-embed-text"))
    assert e.value.message == "ollama embed nomic-embed-text: cannot reach Ollama at http://ollama (ConnectError)"


def test_a_model_that_does_not_answer_in_time_is_a_timeout():
    from kairos_contracts.schema import ChatMessage, ModelRequest, Role

    p, _ = provider(_raise(httpx.ReadTimeout("")))
    with pytest.raises(KairosError) as e:
        asyncio.run(p.generate(ModelRequest(messages=[ChatMessage(role=Role.USER, content="hi")]), "qwen2.5:7b-instruct"))
    assert e.value.code == "TIMEOUT"
    assert e.value.message == "ollama qwen2.5:7b-instruct: no answer within 180s (ReadTimeout)"


def test_nomic_gets_its_task_prefix_and_other_models_do_not():
    from kairos_models.providers.ollama import task_prefixed

    q = EmbedRequest(texts=["why over budget?"], input_type="query")
    d = EmbedRequest(texts=["Apollo budget"], input_type="document")
    assert task_prefixed("nomic-embed-text", q) == ["search_query: why over budget?"]
    assert task_prefixed("nomic-embed-text:latest", d) == ["search_document: Apollo budget"]
    assert task_prefixed("nomic-embed-text", EmbedRequest(texts=["x"])) == ["x"], "no type, no prefix"
    assert task_prefixed("mxbai-embed-large", q) == ["why over budget?"], "only models trained with the prefixes get them"
