# Kết quả tổng hợp — Test set

| Model                  |    Acc |   Balanced Acc |   Precision |   Recall |     F1 |   AUC / Kappa |
|:-----------------------|-------:|---------------:|------------:|---------:|-------:|--------------:|
| Binary EfficientNet-B0 | 0.8626 |         0.8553 |      0.8056 |   0.8274 | 0.8163 |        0.9366 |
| Multi-class (8 lớp)    | 0.8163 |         0.7815 |    nan      | nan      | 0.7547 |        0.7305 |
| Multi-class → Binary   | 0.8842 |         0.874  |      0.8486 |   0.8352 | 0.8418 |        0.9283 |