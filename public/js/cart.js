// The shopping basket.
//
// This store's stock is only ever held by a reservation -- there is no
// separate "cart" table on the server, and inventing one would put stock in
// two places at once. So the basket lives on this device: it is a shopping
// list you build while browsing, and checkout turns the whole list into real
// reservations (the same call "Hold for 1 hour" makes for a single item).
//
// That keeps the rule the rest of the app depends on: available = on_hand -
// reserved, and nothing is held until the store is actually told to hold it.

const KEY = 'cart';

function read() {
  try {
    const rows = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(rows) ? rows.filter((r) => r && r.variant_id) : [];
  } catch {
    return [];
  }
}

function write(rows) {
  localStorage.setItem(KEY, JSON.stringify(rows));
  window.dispatchEvent(new CustomEvent('cartchange'));
  return rows;
}

export const cart = {
  items: read,

  count() {
    return read().reduce((n, r) => n + r.quantity, 0);
  },

  total() {
    return read().reduce((sum, r) => sum + r.price * r.quantity, 0);
  },

  has(variantId) {
    return read().some((r) => r.variant_id === variantId);
  },

  /** Adding the same variant twice bumps the quantity rather than doubling
      the line -- but never past what the shelf actually has. */
  add(product, variant, quantity = 1) {
    const rows = read();
    const line = rows.find((r) => r.variant_id === variant.id);
    const stock = variant.stock?.available ?? 0;

    if (line) {
      line.quantity = Math.min(line.quantity + quantity, Math.max(stock, 1));
    } else {
      rows.push({
        variant_id: variant.id,
        product_id: product.id,
        name: product.name,
        brand: product.brand || '',
        label: variant.label || '',
        sku: variant.sku,
        price: variant.price,
        image_url: product.image_url || '',
        category: product.category || '',
        quantity: Math.min(quantity, Math.max(stock, 1)),
      });
    }
    write(rows);
    return rows;
  },

  setQuantity(variantId, quantity) {
    const rows = read();
    const line = rows.find((r) => r.variant_id === variantId);
    if (!line) return rows;
    if (quantity <= 0) return write(rows.filter((r) => r.variant_id !== variantId));
    line.quantity = quantity;
    return write(rows);
  },

  remove(variantId) {
    return write(read().filter((r) => r.variant_id !== variantId));
  },

  clear() {
    return write([]);
  },
};
