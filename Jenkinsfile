pipeline {
    agent any

    environment {
        PYTHON_VERSION = '3.12'
        IMAGE_NAME = 'fraudguard-app'
        IMAGE_TAG = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout Code') {
            steps {
                echo 'Checking out source repository...'
                checkout scm
            }
        }

        stage('Install Backend & Run Security Tests') {
            steps {
                echo 'Running pytest validation suite and LightGBM inference checks...'
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    pytest tests/ -p no:langsmith -q
                '''
            }
        }

        stage('Frontend Build & Lint') {
            steps {
                dir('frontend') {
                    echo 'Building production React artifacts...'
                    sh '''
                        npm ci
                        npm run build
                    '''
                }
            }
        }

        stage('Docker Image Build') {
            steps {
                echo 'Building container image...'
                sh '''
                    docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -t ${IMAGE_NAME}:latest .
                '''
            }
        }

        stage('Deploy to Kubernetes') {
            when {
                branch 'main'
            }
            steps {
                echo 'Applying Kubernetes manifests...'
                sh '''
                    kubectl apply -f k8s/configmap.yaml
                    kubectl apply -f k8s/secret.yaml
                    kubectl apply -f k8s/deployment.yaml
                    kubectl apply -f k8s/service.yaml
                    kubectl rollout status deployment/fraudguard-deployment --timeout=120s
                '''
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        success {
            echo 'FraudGuard CI/CD Pipeline completed successfully.'
        }
        failure {
            echo 'FraudGuard pipeline failed. Check console output.'
        }
    }
}
