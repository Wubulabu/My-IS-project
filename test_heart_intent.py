#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import app


def _search(query: str, method: str = "hybrid", top_k: int = 8):
    with app.test_client() as client:
        resp = client.post(
            "/api/search",
            json={"query": query, "method": method, "top_k": top_k},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        return resp.get_json()["results"]


def test_chinese_heart_query_prioritizes_literal_heart():
    results = _search("\u7231\u5fc3")
    assert results[0]["en"] == "red heart"
    assert results[0].get("semantic_category") == "Hearts & Love"
    assert all(item.get("semantic_category") == "Hearts & Love" for item in results[:5])


def test_english_heart_query_demotes_non_literal_love_results():
    results = _search("love heart")
    top_names = [item["en"] for item in results[:5]]
    assert "red heart" in top_names
    assert "love letter" not in top_names
    assert "love hotel" not in top_names


if __name__ == "__main__":
    test_chinese_heart_query_prioritizes_literal_heart()
    test_english_heart_query_demotes_non_literal_love_results()
    print("heart intent tests passed")
