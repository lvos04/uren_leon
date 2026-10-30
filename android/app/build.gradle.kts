plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "nl.leon.uren"
    compileSdk = 35

    defaultConfig {
        applicationId = "nl.leon.uren"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    signingConfigs {
        // Release-ondertekening via omgevingsvariabelen (GitHub Actions secrets); anders debug-sleutel.
        create("release") {
            val ks = System.getenv("UREN_KEYSTORE")
            if (ks != null && file(ks).exists()) {
                storeFile = file(ks)
                storePassword = System.getenv("UREN_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("UREN_KEY_ALIAS")
                keyPassword = System.getenv("UREN_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            val rel = signingConfigs.getByName("release")
            signingConfig = if (rel.storeFile != null) rel else signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.work:work-runtime-ktx:2.10.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
