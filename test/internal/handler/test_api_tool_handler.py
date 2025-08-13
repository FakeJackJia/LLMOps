import pytest
from pkg.response import HttpCode


openapi_schema_string = """{"server":"https://weather.example.com","description":"123","paths":{"/location":{"get":{"description":"获取特定位置的天气预报信息","operationId":"GetCurrentWeather","parameters":[{"name":"location","in":"query","description":"需要获取天气预报的城市名","required":true,"type":"str"}]}}}}"""

class TestApiToolHanlder:
    """自定义API工具测试类"""

    @pytest.mark.parametrize("openapi_schema", ["123", openapi_schema_string])
    def test_validate_openapi_schema(self, openapi_schema, client):
        resp = client.post("/api-tools/validate-openapi-schema", json={"openapi_schema": openapi_schema})
        assert resp.status_code == 200
        if openapi_schema == "123":
            assert resp.json.get("code") == HttpCode.VALIDATE_ERROR
        elif openapi_schema == openapi_schema_string:
            assert resp.json.get("code") == HttpCode.SUCCESS


    def test_delete_api_tool_provider(self, client, db):
        provider_id = "f637668c-327d-47f0-9c22-295ec882f912"
        resp = client.post(f"/api-tools/{provider_id}/delete")
        assert resp.status_code == 200

        from internal.model import ApiToolProvider
        api_tool_provider = db.session.query(ApiToolProvider).get(provider_id)
        assert api_tool_provider is None