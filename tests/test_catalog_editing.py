"""Adding and editing the catalogue by hand, from the store side.

Before this, the only way a product ever existed was seed.py or a push from
the parent platform — there was no local write path at all, despite
product.create/product.edit already being in the permission matrix. These
tests are about the same things every other write in this app is: the right
role, a name that cannot be blank, a SKU that cannot collide, and a variant
that cannot be deleted out from under a product that needs at least one.
"""
from services import catalog


def _product(**overrides):
    body = {"name": "Test Product", "brand": "TestCo", "category": "Misc"}
    body.update(overrides)
    return body


def _variant(**overrides):
    body = {"sku": "TEST-SKU-1", "label": "", "price": 99.0}
    body.update(overrides)
    return body


# -- authorization --------------------------------------------------------


def test_creating_a_product_needs_a_token(client):
    assert client.post("/api/products", json=_product()).status_code == 401


def test_staff_cannot_create_a_product(client, staff_headers):
    res = client.post("/api/products", json=_product(), headers=staff_headers)
    assert res.status_code == 403


def test_manager_can_create_a_product(client, manager_headers):
    res = client.post("/api/products", json=_product(), headers=manager_headers)
    assert res.status_code == 201


def test_staff_cannot_delete_a_product(client, manager_headers, owner_headers):
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    res = client.delete(f"/api/products/{created['id']}", headers=manager_headers)
    assert res.status_code == 403, "product.delete is owner-only"


# -- creating -----------------------------------------------------------------


def test_a_product_needs_a_name(client, owner_headers):
    res = client.post("/api/products", json=_product(name=""), headers=owner_headers)
    assert res.status_code == 400
    assert "name" in res.get_json()["error"]


def test_a_created_product_is_findable(client, owner_headers):
    client.post("/api/products", json=_product(name="Unique Widget"), headers=owner_headers)
    found = catalog.list_products(search="Unique Widget")
    assert len(found) == 1


def test_a_variant_needs_a_sku(client, owner_headers):
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    res = client.post(
        f"/api/products/{created['id']}/variants", json=_variant(sku=""), headers=owner_headers
    )
    assert res.status_code == 400


def test_a_duplicate_sku_is_refused_on_create(client, owner_headers):
    p1 = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    p2 = client.post("/api/products", json=_product(name="Second"), headers=owner_headers).get_json()
    client.post(f"/api/products/{p1['id']}/variants", json=_variant(sku="DUP-1"), headers=owner_headers)

    res = client.post(
        f"/api/products/{p2['id']}/variants", json=_variant(sku="DUP-1"), headers=owner_headers
    )
    assert res.status_code == 400
    assert "already in use" in res.get_json()["error"]


def test_a_new_product_shows_up_in_inventory_once_it_has_a_variant(client, owner_headers):
    created = client.post("/api/products", json=_product(name="Findable Item"), headers=owner_headers).get_json()
    client.post(
        f"/api/products/{created['id']}/variants", json=_variant(sku="FIND-1"), headers=owner_headers
    )

    res = client.get("/api/inventory", headers=owner_headers)
    skus = [r["sku"] for r in res.get_json()]
    assert "FIND-1" in skus


# -- editing --------------------------------------------------------------


def test_updating_a_product_changes_only_what_was_sent(client, owner_headers):
    created = client.post(
        "/api/products", json=_product(name="Original", brand="OrigBrand"), headers=owner_headers
    ).get_json()

    res = client.put(f"/api/products/{created['id']}", json={"name": "Renamed"}, headers=owner_headers)

    body = res.get_json()
    assert body["name"] == "Renamed"
    assert body["brand"] == "OrigBrand", "a field not sent must not be blanked out"


def test_a_product_can_be_created_with_a_photo(client, owner_headers):
    photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    created = client.post(
        "/api/products", json=_product(image_url=photo), headers=owner_headers
    ).get_json()
    assert created["image_url"] == photo


def test_updating_a_product_without_a_photo_field_keeps_the_existing_one(client, owner_headers):
    photo = "data:image/png;base64,AAAA"
    created = client.post(
        "/api/products", json=_product(image_url=photo), headers=owner_headers
    ).get_json()

    res = client.put(f"/api/products/{created['id']}", json={"name": "Renamed"}, headers=owner_headers)

    assert res.get_json()["image_url"] == photo, "a save that never touched the photo must not clear it"


def test_updating_with_an_explicit_blank_photo_clears_it(client, owner_headers):
    created = client.post(
        "/api/products", json=_product(image_url="data:image/png;base64,AAAA"), headers=owner_headers
    ).get_json()

    res = client.put(f"/api/products/{created['id']}", json={"image_url": ""}, headers=owner_headers)

    assert res.get_json()["image_url"] == ""


def test_renaming_to_blank_is_refused(client, owner_headers):
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    res = client.put(f"/api/products/{created['id']}", json={"name": "  "}, headers=owner_headers)
    assert res.status_code == 400


def test_updating_a_variant_sku_to_one_already_in_use_is_refused(client, owner_headers):
    p1 = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    client.post(f"/api/products/{p1['id']}/variants", json=_variant(sku="TAKEN"), headers=owner_headers)
    p2 = client.post("/api/products", json=_product(name="P2"), headers=owner_headers).get_json()
    v2 = client.post(
        f"/api/products/{p2['id']}/variants", json=_variant(sku="MINE"), headers=owner_headers
    ).get_json()

    res = client.put(f"/api/variants/{v2['id']}", json={"sku": "TAKEN"}, headers=owner_headers)
    assert res.status_code == 400


def test_a_variant_can_keep_its_own_sku_when_updating_other_fields(client, owner_headers):
    """Regression check: comparing a SKU against itself must not look like a collision."""
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    variant = client.post(
        f"/api/products/{created['id']}/variants", json=_variant(sku="KEEP-1"), headers=owner_headers
    ).get_json()

    res = client.put(
        f"/api/variants/{variant['id']}", json={"sku": "KEEP-1", "price": 150}, headers=owner_headers
    )
    assert res.status_code == 200
    assert res.get_json()["price"] == 150


# -- deleting -------------------------------------------------------------


def test_deleting_a_products_only_variant_is_refused(client, owner_headers):
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    variant = client.post(
        f"/api/products/{created['id']}/variants", json=_variant(), headers=owner_headers
    ).get_json()

    res = client.delete(f"/api/variants/{variant['id']}", headers=owner_headers)

    assert res.status_code == 400
    assert "at least one variant" in res.get_json()["error"]


def test_deleting_one_of_two_variants_succeeds(client, owner_headers):
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    v1 = client.post(
        f"/api/products/{created['id']}/variants", json=_variant(sku="V1"), headers=owner_headers
    ).get_json()
    client.post(f"/api/products/{created['id']}/variants", json=_variant(sku="V2"), headers=owner_headers)

    res = client.delete(f"/api/variants/{v1['id']}", headers=owner_headers)
    assert res.status_code == 204


def test_deleting_a_product_removes_its_variants_too(client, owner_headers):
    created = client.post("/api/products", json=_product(), headers=owner_headers).get_json()
    client.post(
        f"/api/products/{created['id']}/variants", json=_variant(sku="GONE-1"), headers=owner_headers
    )

    res = client.delete(f"/api/products/{created['id']}", headers=owner_headers)

    assert res.status_code == 204
    assert client.get(f"/api/products/{created['id']}").status_code == 404
    assert not any(r["sku"] == "GONE-1" for r in client.get("/api/inventory", headers=owner_headers).get_json())


# -- audit ------------------------------------------------------------------


def test_creating_and_editing_a_product_is_audited(client, owner_headers):
    created = client.post("/api/products", json=_product(name="Audited"), headers=owner_headers).get_json()
    client.put(f"/api/products/{created['id']}", json={"name": "Audited 2"}, headers=owner_headers)

    entries = client.get("/api/audit", headers=owner_headers).get_json()
    actions = [e["action"] for e in entries]
    assert "product.create" in actions
    assert "product.edit" in actions
