# About

Those who attempt to play the global version of sif2 may had already noticed that the client is very unstable, for it's always crash after pop "An error has occurred" window.

I analysed the log, and I found the reason is that the global version of sif2 client always enquiries an nonexistent Google Play product after tap screen, eventually causes Unity IAP Initialize Error, which is a fatal error. Such logic doesn't exist in the japan version of client, so the JP version is fine.

I made a patch script to fix this problem by blocking Google Play Billing Client functions from triggering.

The second script will fix the problem mentioned above as well as modify the client's CDN settings to localhost, it is mainly designed for ZH-CHT language pack support. You can ignore it if you don't need Traditional Chinese support.


p.s. the project's name is based on whose support color matches project's the primary language's color on github :)
<img width="600" height="496" alt="_1689611472_49ac86d2" src="https://github.com/user-attachments/assets/05916e78-1b59-4bdd-9b65-5813a95b572f" />
