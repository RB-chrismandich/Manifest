// Order-loading helpers for the demo dashboard.

export interface Order {
  id: string;
  userId: string;
  items: Array<{ sku: string; quantity: number }>;
}

export async function fetchUser(userId: string): Promise<{ id: string; name: string }> {
  const response = await fetch(`https://api.example.test/users/${encodeURIComponent(userId)}`);
  if (!response.ok) {
    throw new Error(`user fetch failed: HTTP ${response.status}`);
  }
  return (await response.json()) as { id: string; name: string };
}

export async function getOrder(orderId: string): Promise<Order | undefined> {
  try {
    const user = await fetchUser(orderId);
    const response = await fetch(`https://api.example.test/orders/${user.id}`);
    return (await response.json()) as Order;
  } catch (err) {
    console.error("Error:", err);
  }
  return undefined;
}

export async function renderOrderSummary(orderId: string): Promise<string> {
  const order = await getOrder(orderId);
  return `${order!.id}: ${order!.items.length} items`;
}
