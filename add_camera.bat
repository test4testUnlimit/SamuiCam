@echo off
chcp 65001 >nul
echo.
echo  =============================================
echo   SamuiCam — Add New Camera
echo  =============================================
echo.
echo  IMPORTANT: copy the link from the browser address bar!
echo.
echo  CORRECT:   https://www.youtube.com/watch?v=XXXXXXXXXXX
echo  WRONG:     https://youtu.be/XXXXXXXXXXX  (Share button)
echo.
echo  NAMING STANDARD:
echo  [Place Name], [Area/City][ — Suffix]
echo.
echo  Examples:
echo    Crystal Bay Yacht Club, Lamai
echo    Crystal Bay Yacht Club, Lamai --- Panoramic
echo    Seychelles Ocean, Mahe --- 4K
echo    NASA ISS --- Live
echo.
echo  Optional suffixes:  Panoramic / 4K / Live / Rooftop / Underwater
echo.
echo  GROUPS (use exact label):
echo    TH . Thailand
echo    SC . Seychelles
echo    MV . Maldives
echo    US . Hawaii
echo    Caribbean
echo    PH . Philippines
echo    CH . Switzerland
echo    Space
echo.
echo  =============================================
echo.
python add_camera.py
pause