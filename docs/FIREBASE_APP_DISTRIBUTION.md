# Firebase App Distribution — RegIntel

Mirrors the RoomCraft setup (`docs/FIREBASE_APP_DISTRIBUTION.md` in RoomCraft).

## Project status

| Item | Value |
|------|--------|
| Firebase project | `roomcraft-e1312` (shared with RoomCraft) |
| Android package | `com.logicrequire.regintel` |
| App ID | `1:768748224321:android:6646eb31cbd2270e0fabc0` |
| Service account | `firebase-adminsdk-fbsvc@roomcraft-e1312.iam.gserviceaccount.com` |
| GitHub secrets | `FIREBASE_ANDROID_APP_ID`, `FIREBASE_SERVICE_ACCOUNT`, `FIREBASE_TESTER_GROUPS` on `tmai-tech/regintel` |
| Tester group | `testers` (same group alias as RoomCraft) |

## One-time IAM (already done for RoomCraft)

If App Distribution fails, grant the Admin SDK service account:

1. IAM: https://console.cloud.google.com/iam-admin/iam?project=roomcraft-e1312  
2. Principal: `firebase-adminsdk-fbsvc@roomcraft-e1312.iam.gserviceaccount.com`  
3. Role: **Firebase App Distribution Admin** (`roles/firebaseappdistro.admin`)  
4. Enable API: https://console.cloud.google.com/apis/library/firebaseappdistribution.googleapis.com?project=roomcraft-e1312  

## Set GitHub secrets

```bash
./scripts/set-firebase-secrets.sh \
  --app-id '1:768748224321:android:6646eb31cbd2270e0fabc0' \
  --service-account ./.secrets/roomcraft-e1312-firebase-adminsdk-fbsvc.json \
  --groups testers \
  --repo tmai-tech/regintel
```

## Distribute

```bash
gh workflow run "Build APK" --repo tmai-tech/regintel --ref main
```

Or push to `main` / `dev`.

## How testers install

1. Invite email from [Firebase App Distribution](https://console.firebase.google.com/project/roomcraft-e1312/appdistribution)  
2. Open link on Android → install **Firebase App Tester** if prompted  
3. Download **RegIntel** build  

## Console

- App Distribution: https://console.firebase.google.com/project/roomcraft-e1312/appdistribution  
- Firestore data: collections `regintel_*`  
