import pytest
from pkg.response import HttpCode

class TestAppHandler:
    """app控制器的测试类"""

    @pytest.mark.parametrize(
        "app_id, query",
        [
            ("aab6b349-5ca3-4753-bb21-2bbab7712a51", None),
            ("aab6b349-5ca3-4753-bb21-2bbab7712a51", "你好你是?")
        ]
    )
    def test_completion(self, app_id, query, client):
        resp = client.post(f"/apps/{app_id}/debug", json={"query": query})
        assert resp.status_code == 200
        if query is None:
            assert resp.json.get("code") == HttpCode.VALIDATE_ERROR
        else:
            assert resp.json.get("code") == HttpCode.SUCCESS