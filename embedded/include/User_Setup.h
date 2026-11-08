// TFT_eSPI pinout for the 4.0" ST7796 Cheap Yellow Display.
// Same wiring Kori brought up: include/User_Setup.h in DuckyDaBucky/Kori.

#define USER_SETUP_INFO "Kori ST7796 480x320"

#define ST7796_DRIVER

#define TFT_WIDTH 320
#define TFT_HEIGHT 480

#define TFT_BL 27
#define TFT_BACKLIGHT_ON HIGH

#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS 15
#define TFT_DC 2
#define TFT_RST -1

#define TOUCH_CS 33

#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4

#define SPI_FREQUENCY 80000000
#define SPI_READ_FREQUENCY 20000000
#define SPI_TOUCH_FREQUENCY 2500000
