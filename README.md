# sensor.personalcapital
Personal Capital component for [Home Assistant](https://www.home-assistant.io/)

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE.md)

![Project Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]


## Support
Hey dude! Help me out for a couple of :beers: or a :coffee:!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](buymeacoffee.com/churchillhd)

To get started put all contents of `/custom_components/personalcapital/` here:
`<config directory>/custom_components/personalcapital/`. 

**Example configuration.yaml:**

```yaml
sensor:
  platform: personalcapital
  email: chotaling1@someemail.com
  password: 12345
  unit_of_measurement: USD
  monitored_categories:
    - investment
    - cash
```

**Configuration variables:**

key | description
:--- | :---
**platform (Required)** | `personalcapital``
**email (Required)** | Email for personalcapital.com
**password (Required)** | Password for personalcapital.com
**unit_of_measurement (Optional)** | Unit of measurement for your accounts **Default** USD
**monitored_categories (Optional)** | Banking categories to monitor. By default all categories are monitored. Options are `investment, mortgage, cash, other_asset, other_liability, credit, loan` 
***

**Note: You'll get a text message with your pin code to use on the frontend to configure. To do so, go to your entities list, and search for Personal Capital. You should see an entity with type `configurator`**

Due to how `custom_components` are loaded, it is normal to see a `ModuleNotFoundError` error on first boot after adding this, to resolve it, restart Home-Assistant.

[commits-shield]: https://img.shields.io/github/commit-activity/y/chotaling1/sensor.personalcapital.svg?style=for-the-badge
[commits]: https://github.com/chotaling1/sensor.personalcapital/commits/master
[license-shield]: https://img.shields.io/github/license/chotaling1/sensor.personalcapital.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Chuck%20Hotaling%20%40chotaling-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/chotaling1/sensor.personalcapital.svg?style=for-the-badge
[releases]: https://github.com/chotaling1/sensor.personalcapital/releases
