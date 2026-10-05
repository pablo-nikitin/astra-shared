# astra-shared
Общий код и ресурсы Astra

## Модули

- `astra_shared.astro` (extra `astro`) — эфемериды JPL DE421 через Skyfield и
  расчёт натальной карты (планеты, ASC/MC, дома Плацида, средние лунный узел и
  Лилит). Каталог с `de421.bsp` передаётся в `Ephemeris(directory)`; если файла
  нет, Skyfield скачивает его при создании.
