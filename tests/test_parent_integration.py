"""The parent platform's catalogue push and inventory pull.

A different trust boundary from the rest of the API: the caller is head
office's own software, not a person, authenticated by a shared token rather
than a staff session. The tests that matter most are the isolation ones --
that a parent token cannot reach staff-only data, that a staff token cannot
touch the catalogue-push endpoint, and that pushing twice updates rather than
duplicates.
"""
import config
from conftest import TEST_PARENT_TOKEN
from services import catalog


def _product(ref, **overrides):
    body = {
        "parent_ref": ref,
        "name": "Basmati Rice 5kg",
        "brand": "Kishan",
        "category": "Grocery",
        "variants": [
            {"parent_ref": f"{ref}-v1", "sku": f"SKU-{ref}", "label": "", "price": 420.0},
        ],
    }
    body.update(overrides)
    return body


# -- authentication -----------------------------------------------------------


def test_no_token_is_refused(client):
    res = client.post("/api/parent/catalog", json={"products": []})
    assert res.status_code == 401


def test_a_wrong_token_is_refused(client):
    res = client.post(
        "/api/parent/catalog", json={"products": []}, headers={"X-Parent-Token": "not-it"}
    )
    assert res.status_code == 401


def test_an_unconfigured_installation_hides_the_endpoint(client, monkeypatch):
    """No PARENT_TOKEN set: looks like the endpoint does not exist, not like
    it exists but is locked -- the same posture DEMO_MODE takes when off."""
    monkeypatch.setattr(config, "PARENT_TOKEN", None)
    res = client.post(
        "/api/parent/catalog", json={"products": []}, headers={"X-Parent-Token": "anything"}
    )
    assert res.status_code == 404


def test_a_staff_session_token_does_not_work_here(client, owner_headers):
    """The two credential schemes must not be interchangeable."""
    res = client.post("/api/parent/catalog", json={"products": []}, headers=owner_headers)
    assert res.status_code == 401


def test_a_parent_token_does_not_work_on_staff_endpoints(client, parent_headers):
    """Isolation the other way: catalogue access is not a backdoor into staff data."""
    res = client.get("/api/staff", headers=parent_headers)
    assert res.status_code == 401


# -- pushing the catalogue -----------------------------------------------------


def test_a_push_creates_a_product_and_variant(client, parent_headers):
    res = client.post(
        "/api/parent/catalog",
        json={"store_id": config.STORE_ID, "products": [_product("p-1")]},
        headers=parent_headers,
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body == {"ok": True, "products": 1, "products_created": 1, "variants": 1, "variants_created": 1}


def test_a_pushed_product_is_real_in_the_store(client, parent_headers):
    """Not just a row in a private table -- it must show up where a customer looks."""
    client.post(
        "/api/parent/catalog",
        json={"products": [_product("p-2", name="Sunflower Oil 1L")]},
        headers=parent_headers,
    )
    # Searched by SKU, not by a word from the name: the seeded catalogue has
    # its own sunflower oil, and this test is about the pushed row.
    found = catalog.list_products(search="SKU-p-2")
    assert found and found[0]["name"] == "Sunflower Oil 1L"
    assert found[0]["variants"][0]["sku"] == "SKU-p-2"


def test_pushing_the_same_ref_again_updates_rather_than_duplicates(client, parent_headers):
    client.post("/api/parent/catalog", json={"products": [_product("p-3")]}, headers=parent_headers)

    res = client.post(
        "/api/parent/catalog",
        json={"products": [_product("p-3", name="Basmati Rice 10kg")]},
        headers=parent_headers,
    )

    assert res.get_json() == {
        "ok": True, "products": 1, "products_created": 0, "variants": 1, "variants_created": 0
    }
    matches = catalog.list_products(search="SKU-p-3")
    assert len(matches) == 1, "a second push must not create a second product"
    assert matches[0]["name"] == "Basmati Rice 10kg"


def test_renaming_a_product_at_head_office_renames_it_here_too(client, parent_headers):
    """The whole point of matching by parent_ref instead of name."""
    client.post(
        "/api/parent/catalog",
        json={"products": [_product("p-4", name="Rice 5kg")]},
        headers=parent_headers,
    )
    client.post(
        "/api/parent/catalog",
        json={"products": [_product("p-4", name="Premium Basmati Rice 5kg")]},
        headers=parent_headers,
    )

    names = {p["name"] for p in catalog.list_products(search="SKU-p-4")}
    assert names == {"Premium Basmati Rice 5kg"}, "renaming must update the one row, not add a second"


def test_a_product_with_no_parent_ref_is_refused(client, parent_headers):
    bad = _product("p-5")
    del bad["parent_ref"]
    res = client.post("/api/parent/catalog", json={"products": [bad]}, headers=parent_headers)
    assert res.status_code == 400
    assert "parent_ref" in res.get_json()["error"]


def test_a_variant_with_no_sku_is_refused(client, parent_headers):
    bad = _product("p-6")
    bad["variants"][0]["sku"] = ""
    res = client.post("/api/parent/catalog", json={"products": [bad]}, headers=parent_headers)
    assert res.status_code == 400


def test_one_bad_item_rolls_back_the_whole_push(client, parent_headers):
    """All-or-nothing: a malformed item partway through must not leave a
    half-applied catalogue behind."""
    good = _product("p-7", name="Should Not Be Saved")
    bad = _product("p-8")
    del bad["parent_ref"]

    res = client.post(
        "/api/parent/catalog", json={"products": [good, bad]}, headers=parent_headers
    )

    assert res.status_code == 400
    assert not catalog.list_products(search="Should Not Be Saved")


def test_a_mismatched_store_id_is_refused(client, parent_headers):
    res = client.post(
        "/api/parent/catalog",
        json={"store_id": "SOME-OTHER-STORE", "products": [_product("p-9")]},
        headers=parent_headers,
    )
    assert res.status_code == 400


# -- pulling inventory ----------------------------------------------------------


def test_pulling_inventory_reflects_real_stock(client, parent_headers, owner_headers):
    client.post("/api/parent/catalog", json={"products": [_product("p-10")]}, headers=parent_headers)
    variant = catalog.find_by_code("SKU-p-10")
    client.post(
        f"/api/inventory/{variant['id']}/movement",
        json={"kind": "add", "quantity": 25},
        headers=owner_headers,
    )

    res = client.get("/api/parent/inventory", headers=parent_headers)

    assert res.status_code == 200
    body = res.get_json()
    row = next(r for r in body["items"] if r["sku"] == "SKU-p-10")
    assert row["on_hand"] == 25
    assert row["available"] == 25
    assert row["parent_ref"] == "p-10-v1"


def test_pulled_inventory_never_includes_customer_or_staff_data(client, parent_headers):
    """Field names only -- a naive text scan would false-positive on product
    names like 'Bluetooth Headphones' containing the substring 'phone'."""
    res = client.get("/api/parent/inventory", headers=parent_headers)
    body = res.get_json()
    allowed = {"parent_ref", "sku", "product_name", "on_hand", "reserved", "available", "updated_at"}
    for row in body["items"]:
        assert set(row.keys()) <= allowed, f"unexpected field(s) leaked: {set(row) - allowed}"
