---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Can you review this diff for performance? The /orders page got slow after it landed.

```diff
--- a/shop/views.py
+++ b/shop/views.py
@@ -12,6 +12,10 @@ def order_list(request):
-    orders = Order.objects.filter(user=request.user).select_related("product")
+    orders = Order.objects.filter(user=request.user)
+    rows = []
+    for o in orders:
+        rows.append({"id": o.id, "product": o.product.name, "price": o.product.price})
-    return render(request, "orders.html", {"orders": orders})
+    return render(request, "orders.html", {"rows": rows})
```
