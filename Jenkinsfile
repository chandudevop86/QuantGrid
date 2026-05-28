pipeline {
  agent any

  options {
    timestamps()
    ansiColor('xterm')
    disableConcurrentBuilds()
  }

  environment {
    PYTHONUNBUFFERED = '1'
    PIP_DISABLE_PIP_VERSION_CHECK = '1'
    FRONTEND_DIR = 'apps/frontend'
    BACKEND_DIR = 'services/trading-service'
    STAGING_URL = "${env.QUANTGRID_STAGING_URL}"
    PRODUCTION_URL = "${env.QUANTGRID_PRODUCTION_URL}"
    PRODUCTION_DEPLOY_STARTED = 'false'
  }

  stages {
    stage('Checkout') {
      steps {
        echo 'Checking out QuantGrid source'
        checkout scm
      }
    }

    stage('Backend setup') {
      steps {
        echo 'Installing backend quality and runtime dependencies'
        sh 'python -m pip install --upgrade pip'
        sh 'pip install -r requirements-dev.txt'
      }
    }

    stage('Backend lint with ruff') {
      steps {
        echo 'Running ruff lint'
        sh 'ruff check services/trading-service tests'
      }
    }

    stage('Backend tests with pytest') {
      steps {
        echo 'Running pytest with coverage'
        withCredentials([
          string(credentialsId: 'quantgrid-database-url', variable: 'DATABASE_URL'),
          string(credentialsId: 'quantgrid-auth-secret', variable: 'QUANTGRID_AUTH_SECRET')
        ]) {
          sh label: 'Run pytest and fail pipeline on test failure', script: '''
            set -eu
            QUANTGRID_ENV=local QUANTGRID_ALLOW_DEV_SEED_USERS=true \
              python -m pytest tests \
                --cov=services/trading-service/Backend \
                --cov-report=term-missing \
                --cov-fail-under=45
          '''
        }
      }
    }

    stage('Security scan with bandit') {
      steps {
        echo 'Running bandit and secret/config checks'
        sh 'bandit -q -r services/trading-service -x "*/tests/*"'
        sh 'python scripts/check_no_secrets.py'
        sh 'python scripts/check_production_config.py'
      }
    }

    stage('Frontend install') {
      steps {
        echo 'Installing frontend dependencies'
        dir('apps/frontend') {
          sh 'npm ci'
        }
      }
    }

    stage('Frontend build') {
      steps {
        echo 'Building frontend'
        dir('apps/frontend') {
          sh 'npm run build'
        }
      }
    }

    stage('Docker build validation') {
      steps {
        echo 'Validating Docker Compose configuration'
        withCredentials([usernamePassword(credentialsId: 'quantgrid-docker-registry', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASSWORD')]) {
          sh 'POSTGRES_PASSWORD=ci-postgres-password docker compose -f docker-compose.yml config'
        }
      }
    }

    stage('Terraform validation') {
      steps {
        echo 'Validating Terraform AWS 3-tier infrastructure'
        sh 'terraform fmt -check -recursive infra/terraform'
        dir('infra/terraform/aws') {
          sh 'terraform init -backend=false'
          sh 'terraform validate'
        }
      }
    }

    stage('Validate deployment URLs') {
      steps {
        sh label: 'Require Jenkins deployment URLs', script: '''
          set -eu
          test -n "${STAGING_URL}"
          test -n "${PRODUCTION_URL}"
        '''
      }
    }

    stage('Deploy to staging') {
      when { branch 'main' }
      steps {
        echo 'Deploying to staging'
        sshagent(credentials: ['quantgrid-ssh-deploy-key']) {
          sh 'bash scripts/jenkins/deploy_staging.sh'
        }
      }
    }

    stage('Staging smoke test') {
      when { branch 'main' }
      steps {
        echo 'Running staging smoke test'
        sh 'bash scripts/jenkins/smoke_test.sh "${STAGING_URL}"'
      }
    }

    stage('Manual approval before production') {
      when { branch 'main' }
      steps {
        input message: 'Deploy QuantGrid to production?', ok: 'Deploy production'
      }
    }

    stage('Deploy production') {
      when { branch 'main' }
      steps {
        echo 'Deploying to production'
        script {
          env.PRODUCTION_DEPLOY_STARTED = 'true'
        }
        sshagent(credentials: ['quantgrid-ssh-deploy-key']) {
          sh 'bash scripts/jenkins/deploy_production.sh'
        }
      }
    }

    stage('Post-deploy smoke test') {
      when { branch 'main' }
      steps {
        echo 'Running production smoke test'
        sh 'bash scripts/jenkins/smoke_test.sh "${PRODUCTION_URL}"'
      }
    }
  }

  post {
    failure {
      script {
        if (env.BRANCH_NAME == 'main' && env.PRODUCTION_DEPLOY_STARTED == 'true') {
          echo 'Pipeline failed after production deploy started. Attempting production rollback.'
          sshagent(credentials: ['quantgrid-ssh-deploy-key']) {
            sh 'bash scripts/jenkins/rollback.sh "${ROLLBACK_REF:-HEAD~1}" production'
          }
        } else {
          echo 'Pipeline failed before production deploy. Skipping production rollback.'
        }
      }
    }
  }
}
