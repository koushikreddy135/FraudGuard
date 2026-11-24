# Local Kubernetes deployment

These manifests run the backend and frontend separately. They target the local
Docker Desktop `kind` cluster and use locally imported images with
`imagePullPolicy: Never`.

The backend uses the `standard` StorageClass for its SQLite data volume. This
creates a new Kubernetes volume; it does not migrate or replace the Docker
Compose volume.

Create the `fraudguard-secrets` Secret before applying the deployments. It must
contain `SECRET_KEY`; add `GOOGLE_CLIENT_SECRET` and `SMTP_PASSWORD` if those
integrations are enabled. Do not commit the Secret values.

Apply and check the workloads:

```powershell
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/fraudguard-backend --timeout=5m
kubectl rollout status deployment/fraudguard-frontend --timeout=5m
kubectl get pods,services,pvc
```

On Docker Desktop, forward the frontend Service to the host:

```powershell
kubectl port-forward service/frontend 30080:80
```

Then open <http://localhost:30080>. The backend is available inside the cluster
through the `backend:8000` Service. Register
`http://localhost:30080/api/auth/oauth/google/callback` with the Google OAuth
client if Google sign-in is used.
