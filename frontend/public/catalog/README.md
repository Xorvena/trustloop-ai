# Catalog images

The `*.svg` files here are **original generic illustrations** created for this project (one per product type).
They are **not product photos**. The API labels them `image_source: "illustration"` and the UI shows an
"Illustration" tag so nobody mistakes them for the real product.

To use real photos: add licensed/own images to this folder (e.g. `LT-ASUS-VB16.jpg`) and set the product's
`image_url` to `/catalog/LT-ASUS-VB16.jpg` and `image_source` to `licensed_photo` (or use an absolute https URL you
have the right to use). Do not hotlink retailer images without permission. If `image_url` is null or fails to load,
the UI falls back to a neutral placeholder.
