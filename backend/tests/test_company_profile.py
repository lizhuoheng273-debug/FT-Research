"""公司资料标准化、降级和缓存测试（不访问网络）。"""

import company_profile


def setup_function():
    company_profile.clear_cache()


def test_cninfo_profile_is_normalized_and_cached(monkeypatch):
    calls = {"primary": 0}

    def primary(code):
        calls["primary"] += 1
        return {
            "公司名称": "兆易创新科技集团股份有限公司",
            "英文名称": "GigaDevice Semiconductor Inc.",
            "A股简称": "兆易创新",
            "所属市场": "上交所",
            "所属行业": "半导体",
            "法人代表": "朱一明",
            "注册资金": "29057.85",
            "成立日期": "2005-04-06",
            "上市日期": "2016-08-18",
            "官方网站": "https://www.gigadevice.com",
            "电子邮箱": "example@gigadevice.com",
            "联系电话": "010-00000000",
            "注册地址": "北京市",
            "办公地址": "北京市海淀区",
            "主营业务": "存储器及微控制器研发销售",
            "经营范围": "集成电路产品研发与销售",
            "机构简介": "公司专注于集成电路设计。",
        }

    monkeypatch.setattr(company_profile, "_load_cninfo", primary)
    monkeypatch.setattr(company_profile, "_load_eastmoney", lambda code: {})
    monkeypatch.setattr(company_profile, "_load_partial", lambda code: {})

    first = company_profile.get_company_profile("603986")
    second = company_profile.get_company_profile("603986")

    assert first == second
    assert calls["primary"] == 1
    assert first["shortName"] == "兆易创新"
    assert first["fullName"] == "兆易创新科技集团股份有限公司"
    assert first["registeredCapitalWan"] == 29057.85
    assert first["source"] == "巨潮资讯"
    assert first["partial"] is False
    assert first["stale"] is False


def test_falls_back_to_real_partial_data(monkeypatch):
    monkeypatch.setattr(company_profile, "_load_cninfo", lambda code: {})
    monkeypatch.setattr(company_profile, "_load_eastmoney", lambda code: {})
    monkeypatch.setattr(company_profile, "_load_partial", lambda code: {
        "shortName": "生益科技", "industry": "电子元件"
    })

    result = company_profile.get_company_profile("600183")

    assert result["code"] == "600183"
    assert result["shortName"] == "生益科技"
    assert result["industry"] == "电子元件"
    assert result["partial"] is True
    assert result["source"] == "腾讯行情/东方财富板块"
    assert "companyHistory" in result


def test_does_not_cache_an_empty_unverified_fallback(monkeypatch):
    monkeypatch.setattr(company_profile, "_load_cninfo", lambda code: {})
    monkeypatch.setattr(company_profile, "_load_eastmoney", lambda code: {})
    monkeypatch.setattr(company_profile, "_load_partial", lambda code: {})

    try:
        company_profile.get_company_profile("600183")
    except company_profile.CompanyProfileUnavailable:
        pass
    else:
        raise AssertionError("空的未验证降级结果必须报错")

    monkeypatch.setattr(company_profile, "_load_partial", lambda code: {"shortName": "生益科技"})
    recovered = company_profile.get_company_profile("600183")
    assert recovered["shortName"] == "生益科技"


def test_four_prefix_is_beijing_market():
    assert company_profile._market_for("430047") == "北京证券交易所"
