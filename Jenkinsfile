// FraudGuard CI/CD for Jenkins running natively on WINDOWS (uses `bat` / `powershell` steps).
//
// GitHub push -> webhook -> Jenkins -> pytest (inside Docker) -> docker build -> docker compose up -> health check
//
// Needs on the PC: Docker Desktop (running, Linux containers) and Git. Python, Node and kubectl are
// NOT needed: tests and the frontend build run inside Docker.
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
        IMAGE_NAME           = 'fraudguard-app'
        SECRET_CRED          = 'fraudguard-secret-key' // Jenkins: Secret text (64 hex characters)
        COMPOSE_PROJECT_NAME = 'fraudguard'
        DOCKER_BUILDKIT      = '1'
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
                    def sha = bat(script: '@git rev-parse --short HEAD', returnStdout: true).trim()
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${sha}"
                    echo "Building ${env.IMAGE_NAME}:${env.IMAGE_TAG}"
                }
            }
        }

        stage('Run Tests') {
            steps {
                // Builds the Dockerfile `test` target and runs pytest (58 tests)
                bat 'docker build --target test -t fraudguard-test:%BUILD_NUMBER% .'
                bat 'docker run --rm fraudguard-test:%BUILD_NUMBER%'
            }
        }

        stage('Build Docker Image') {
            steps {
                // The React build (tsc + vite) happens inside the Dockerfile
                bat 'docker build -t %IMAGE_NAME%:%IMAGE_TAG% -t %IMAGE_NAME%:latest .'
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([string(credentialsId: env.SECRET_CRED, variable: 'SECRET_KEY')]) {
                    bat '''
                        set IMAGE=%IMAGE_NAME%
                        docker compose up -d --no-build
                    '''
                }
            }
        }

        stage('Smoke Test') {
            steps {
                // Wait for the container HEALTHCHECK (/health = 200 once the model has loaded)
                powershell '''
                    $containerId = docker compose ps -q fraudguard

                    if (-not $containerId) {
                        Write-Host "FraudGuard container was not found."
                        docker compose logs --tail 100 fraudguard
                        exit 1
                    }

                    for ($i = 0; $i -lt 30; $i++) {
                        $health = docker inspect -f "{{.State.Health.Status}}" $containerId 2>$null

                        Write-Host "Health status: $health"

                        if ($health -eq "healthy") {
                            Write-Host "FraudGuard is healthy!"
                            exit 0
                        }

                        Start-Sleep -Seconds 5
                    }

                    docker compose logs --tail 100 fraudguard
                    exit 1
                 '''
            }
        }
    }

    post {
        success { echo "FraudGuard deployed: ${env.IMAGE_NAME}:${env.IMAGE_TAG} -> http://localhost:8000" }
        failure { echo 'FraudGuard pipeline failed. Check the failing stage in the console output.' }
        always  { bat(script: 'docker image prune -f', returnStatus: true) }
    }
}