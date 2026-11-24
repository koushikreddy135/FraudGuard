// FraudGuard CI/CD for Jenkins running natively on WINDOWS (uses `bat` / `powershell` steps).
//
// GitHub push -> webhook -> Jenkins -> pytest (inside Docker) -> build backend + frontend images
// -> docker compose up -> health check
//
// Needs on the PC: Docker Desktop (running, Linux containers) and Git. Python, Node and kubectl are
// NOT needed: tests and the frontend build run inside Docker. The frontend and backend run in separate containers.
// The job deploys whichever branch it is configured to watch (Branch Specifier in the job).

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)                      // shallow checkout below (repo is large)
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    triggers {
        githubPush()                                   // fired by the GitHub webhook (needs the GitHub plugin)
    }

    environment {
        BACKEND_IMAGE        = 'fraudguard-backend'
        FRONTEND_IMAGE       = 'fraudguard-frontend'
        SECRET_CRED          = 'fraudguard-secret-key' // Jenkins: Secret text (64 hex characters)
        COMPOSE_PROJECT_NAME = 'fraudguard'
        DOCKER_BUILDKIT      = '1'
        // Jenkins runs as a Windows service, so it does not inherit the interactive user's PATH.
        // This is the Docker Desktop CLI location on the development machine.
        PATH = "C:\\Users\\koush\\AppData\\Local\\Programs\\DockerDesktop\\resources\\bin;${env.PATH}"
    }

    stages {

        stage('Checkout Code') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: scm.branches,
                    userRemoteConfigs: scm.userRemoteConfigs,
                    extensions: [[$class: 'CloneOption', shallow: true, depth: 1, noTags: true, timeout: 30]]
                ])
                script {
                    // SCM checkout exports GIT_COMMIT; avoid depending on interactive Git PATH.
                    def sha = env.GIT_COMMIT.take(7)
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${sha}"
                    echo "Building ${env.BACKEND_IMAGE}:${env.IMAGE_TAG} and ${env.FRONTEND_IMAGE}:${env.IMAGE_TAG}"
                }
            }
        }

        stage('Unit Tests') {
            steps {
                echo 'Running backend unit tests with pytest in the Docker test image.'
                bat '''
                    if not exist test-results mkdir test-results
                    docker build --target test -t fraudguard-test:%BUILD_NUMBER% .
                    docker run --rm --mount "type=bind,source=%WORKSPACE%/test-results,target=/reports" fraudguard-test:%BUILD_NUMBER% python -m pytest tests -q --junitxml=/reports/pytest-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results/pytest-results.xml'
                }
            }
        }

        stage('Build Docker Images') {
            steps {
                bat 'docker build --target backend-runtime -t %BACKEND_IMAGE%:%IMAGE_TAG% -t %BACKEND_IMAGE%:latest .'
                bat 'docker build --target frontend-runtime -t %FRONTEND_IMAGE%:%IMAGE_TAG% -t %FRONTEND_IMAGE%:latest .'
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([string(credentialsId: env.SECRET_CRED, variable: 'SECRET_KEY')]) {
                    bat '''
                        docker compose down --remove-orphans
                        docker compose up -d --no-build
                    '''
                }
            }
        }

        stage('Smoke Test') {
            steps {
                // Wait for backend model readiness and for the frontend web server to respond.
                powershell '''
                    $backendId = ([string](docker compose ps -q backend)).Trim()
                    $frontendId = ([string](docker compose ps -q frontend)).Trim()

                    if (-not $backendId -or -not $frontendId) {
                        Write-Host "FraudGuard backend or frontend container was not found."
                        docker compose logs --tail 100 backend frontend
                        exit 1
                    }

                    for ($i = 0; $i -lt 30; $i++) {
                        $backendHealth = docker inspect -f "{{.State.Health.Status}}" $backendId 2>$null
                        $frontendHealth = docker inspect -f "{{.State.Health.Status}}" $frontendId 2>$null

                        Write-Host "Backend health: $backendHealth; frontend health: $frontendHealth"

                        if ($backendHealth -eq "healthy" -and $frontendHealth -eq "healthy") {
                            Write-Host "FraudGuard backend and frontend are healthy!"
                            exit 0
                        }

                        Start-Sleep -Seconds 5
                    }

                    docker compose logs --tail 100 backend frontend
                    exit 1
                 '''
            }
        }
    }

    post {
        success { echo "FraudGuard deployed: ${env.BACKEND_IMAGE}:${env.IMAGE_TAG} + ${env.FRONTEND_IMAGE}:${env.IMAGE_TAG} -> http://localhost:8000" }
        failure { echo 'FraudGuard pipeline failed. Check the failing stage in the console output.' }
        always  { bat(script: 'docker image prune -f', returnStatus: true) }
    }
}
