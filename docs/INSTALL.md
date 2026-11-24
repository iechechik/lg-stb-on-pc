# Перенос системы на другой диск

Порядок замены внутреннего диска без переустановки: разметка нового диска,
копирование файлов, загрузчик, проверка. Имя нового диска в примере — `/dev/sdb`;
перед выполнением команд проверить имя (`lsblk`), иначе можно стереть не тот диск.

## 1. Разметка

```sh
sudo parted -s /dev/sdb mklabel gpt
sudo parted -s /dev/sdb mkpart EFI  fat32 1MiB 1025MiB
sudo parted -s /dev/sdb set 1 esp on
sudo parted -s /dev/sdb mkpart ROOT ext4 1025MiB 100%
sudo mkfs.vfat -F 32 -n EFI /dev/sdb1
sudo mkfs.ext4 -L ROOT /dev/sdb2
```

## 2. Копирование

```sh
sudo mkdir -p /mnt/new && sudo mount /dev/sdb2 /mnt/new
sudo mkdir -p /mnt/new/boot/efi && sudo mount /dev/sdb1 /mnt/new/boot/efi

sudo rsync -aHAX --numeric-ids --info=progress2 \
     --exclude={/proc,/sys,/dev,/run,/tmp,/var/tmp,/mnt,/media,/lost+found,/swapfile} \
     / /mnt/new/
```

## 3. Настройки нового диска

```sh
sudo blkid /dev/sdb2 /dev/sdb1      # новые UUID
sudo nano /mnt/new/etc/fstab        # корень и EFI по UUID

# подкачка файлом
sudo fallocate -l 4G /mnt/new/swapfile
sudo chmod 600 /mnt/new/swapfile
sudo mkswap /mnt/new/swapfile
```

В `fstab` указывать UUID, а не `/dev/sdX`: имена устройств меняются, UUID нет.

## 4. Загрузчик

```sh
sudo mount --bind /dev  /mnt/new/dev
sudo mount --bind /proc /mnt/new/proc
sudo mount --bind /sys  /mnt/new/sys
sudo mount --bind /run  /mnt/new/run
sudo chroot /mnt/new

grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian-ssd
grub-install --target=x86_64-efi --efi-directory=/boot/efi --removable
update-initramfs -u -k all
update-grub
exit
```

Запись `--removable` кладёт `EFI/BOOT/BOOTX64.EFI` прямо на диск: он загрузится,
даже если прошивка не сохранила запись о нём.

## 5. Проверка и установка внутрь корпуса

```sh
sudo umount -R /mnt/new
sudo reboot        # при старте выбрать загрузку с нового диска
```

После успешной загрузки с нового диска — выключить, поставить его на место
прежнего, включить. Если прошивка не нашла систему, выбрать диск в меню загрузки.
Затем записать загрузчик под обычным именем:

```sh
sudo grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian
sudo update-grub
```
