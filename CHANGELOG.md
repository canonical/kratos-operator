# Changelog

## 1.0.0 (2025-11-21)


### ⚠ BREAKING CHANGES

* refactor the charm
* refactor the juju actions
* use kratos external provider library v1

### Features

* add actions to list identifiers and unlink account ([57e2c3c](https://github.com/canonical/kratos-operator/commit/57e2c3cd70d4f98d2e868b79076dd01f5ca1111f))
* add default return url for oidc settings ([6986ae7](https://github.com/canonical/kratos-operator/commit/6986ae763ad9e342dd7db30c0081c5f618fda8f8))
* add terraform module ([1a4eb77](https://github.com/canonical/kratos-operator/commit/1a4eb777575cf789cbaf772d5a1040db2d1073ea))
* add the terraform module ([241729a](https://github.com/canonical/kratos-operator/commit/241729a100da62eb78ab3763c2c318a923a576a6))
* drop ingresses in favour of traefik route ([c868490](https://github.com/canonical/kratos-operator/commit/c8684908fec871de0d8650ee9173b8224c002937))
* implement PublicRoute integration ([b4e91cd](https://github.com/canonical/kratos-operator/commit/b4e91cd2d99ed1a547cc6c52212d0bccd792077e))
* support oidc webauthn sequencing mode ([dea7e4e](https://github.com/canonical/kratos-operator/commit/dea7e4e5315379e8c40133a1c6b064405522612d))
* support oidc webauthn sequencing mode ([b32d5ca](https://github.com/canonical/kratos-operator/commit/b32d5ca57215bfac18899f1f2f65937b8180ff81))
* update juju_application resource name ([836e00f](https://github.com/canonical/kratos-operator/commit/836e00f63623f0e0524ac795ac62dd073cddaef5))


### Bug Fixes

* add collect_status handler ([e441df6](https://github.com/canonical/kratos-operator/commit/e441df62e5133cba19cfe2433fa8d6b43c56cec2))
* add health check handlers ([355b8c0](https://github.com/canonical/kratos-operator/commit/355b8c0b648971890b6679b844520845e6f85a73))
* add kratos_registration_webhook lib ([1f4d132](https://github.com/canonical/kratos-operator/commit/1f4d1321e5cf108a9243185c81f23745965163a5))
* add pod resource constraints ([d3807cb](https://github.com/canonical/kratos-operator/commit/d3807cbb91eca902dccb1fa9c4424829bb514ca9))
* address CVEs ([15b37f0](https://github.com/canonical/kratos-operator/commit/15b37f01f8a717f2003369a0302b1f34bafe6a50)), closes [#372](https://github.com/canonical/kratos-operator/issues/372)
* align the idp k8s configmap key name ([c268413](https://github.com/canonical/kratos-operator/commit/c26841336ae9ee279fdcf28bb65684d7eaec42be))
* align the idp k8s configmap key name ([296da36](https://github.com/canonical/kratos-operator/commit/296da363f077a1cfbac339158b7ac280114a513d))
* bump ingress version ([313091f](https://github.com/canonical/kratos-operator/commit/313091f658e1dce535b0e954c116be074019a085))
* check leadership ([300b10f](https://github.com/canonical/kratos-operator/commit/300b10f101fab7595fd0fe84e541b33f7718afbd))
* check that relation is active ([56b4adc](https://github.com/canonical/kratos-operator/commit/56b4adc4228607f193db5ed162312f47ba61aec4))
* clean up webhook logic ([70be0b6](https://github.com/canonical/kratos-operator/commit/70be0b68025fb48ae441a5a286c30bd342017f84))
* compare config against cm ([94eb584](https://github.com/canonical/kratos-operator/commit/94eb5848ca98ef6611201b250f85a3bc372cf52f))
* do not defer events if not needed ([2eca933](https://github.com/canonical/kratos-operator/commit/2eca9333f6ed28c8868b82e22345ea408e574540))
* downgrade charm lib version ([0c392f3](https://github.com/canonical/kratos-operator/commit/0c392f38a2e3e6810793eda99a1e332bda9bb4bd))
* explicitly disable unsupported methods ([e764823](https://github.com/canonical/kratos-operator/commit/e764823a4c89c0c3d534195573d4739c6762f9c0))
* explicitly disable unsupported methods ([7ebde0d](https://github.com/canonical/kratos-operator/commit/7ebde0da37a8447251f864665c57b5926d2dd4d3))
* fix auth config parsing ([bc74de1](https://github.com/canonical/kratos-operator/commit/bc74de1efb8a17791b3113a3b44efdb4e9ab7ba4))
* fix ca bundle generation ([60f836e](https://github.com/canonical/kratos-operator/commit/60f836e79726c3194c11972c94221bab618b68d8))
* fix constraint ([fc0b1be](https://github.com/canonical/kratos-operator/commit/fc0b1be120e0a241ad14f90f6649717aa3e56e20))
* fix the lint ci ([c731894](https://github.com/canonical/kratos-operator/commit/c731894146f59c49c67583b7bebe4da5497954f0))
* fix the lint ci ([45b9d63](https://github.com/canonical/kratos-operator/commit/45b9d6319fe59a2914ceebd40741d316e13cc10c))
* fix the statefulset's name ([266f06d](https://github.com/canonical/kratos-operator/commit/266f06db554bb2fdf0b565dbdcc9166f5fe4907b))
* fix the statefulset's name ([10c0c52](https://github.com/canonical/kratos-operator/commit/10c0c52d6ae215ada5b7d75b59d8a47cff386fde))
* fix webhook auth ([5702f05](https://github.com/canonical/kratos-operator/commit/5702f0517a12e9f6116eb6c911e5fac3859e1628))
* hardcode relation in constants.py ([72f41fa](https://github.com/canonical/kratos-operator/commit/72f41fad5561720954152a2c9a0c627c754e7d10))
* hardcode relation in constants.py ([6dd8798](https://github.com/canonical/kratos-operator/commit/6dd8798fe5512b9e57366b27c6e4422ceb173b67))
* improve route integration handling logic ([c33d6c8](https://github.com/canonical/kratos-operator/commit/c33d6c865b98674d37166ed022414575aaa88d97))
* improve the error hint for create-admin-account juju action ([50166f8](https://github.com/canonical/kratos-operator/commit/50166f88f08a96850837c894b4c343445277117c))
* improve the error hint for create-admin-account juju action ([0d764cb](https://github.com/canonical/kratos-operator/commit/0d764cb2d7636b24b8fb395ad78f10c3d7639630))
* patch up internal-ingress and rename it internal-route ([79e02bf](https://github.com/canonical/kratos-operator/commit/79e02bf379f1b252abe5ef77870eabee4ecdaed2))
* provide optional flag in charmcraft.yaml ([fc0b664](https://github.com/canonical/kratos-operator/commit/fc0b6644a207ec0cdcfd567866d61982f16ecde1))
* restart service only when config changed ([259a15a](https://github.com/canonical/kratos-operator/commit/259a15af6f1ce3c36e0c9852bffe8aebc7910475))
* skip CHANGELOG.md from spell check ([37042e1](https://github.com/canonical/kratos-operator/commit/37042e115f9b97fe788cafcfe0fe113478af4a64))
* skip CHANGELOG.md from spell check ([7ea81f9](https://github.com/canonical/kratos-operator/commit/7ea81f90386bae2b7e8633f301d6c425b5a130e8))
* stop service when database is gone ([a8d73cc](https://github.com/canonical/kratos-operator/commit/a8d73ccc28ac1288b2d75ebc253404b62daff16d))
* store api token in juju secret ([783228b](https://github.com/canonical/kratos-operator/commit/783228b0a479599706a33d96f380f2e3431e4436))
* switch to use -route relations in the tf module ([a9c1087](https://github.com/canonical/kratos-operator/commit/a9c108729f7a3dde4b2169375aaab1dcc47c8cf4))
* update all external-idp config in holistic handler ([8e517f5](https://github.com/canonical/kratos-operator/commit/8e517f50a2573f0f19c79091ae213619a9c95794))
* update charm dependent libs ([d88c488](https://github.com/canonical/kratos-operator/commit/d88c488bf3e854f541387baec0a46fe6278c7ae2))
* update charm dependent libs ([6f8c2df](https://github.com/canonical/kratos-operator/commit/6f8c2dfaeaeddd14ae2c6930e1865a552edb5770))
* update login_ui lib, add registration_url ([b92f9f0](https://github.com/canonical/kratos-operator/commit/b92f9f0e608e3e3edd80cd0db9ff9786749436c0))
* update run_after_config_updated ([fc8ad80](https://github.com/canonical/kratos-operator/commit/fc8ad802eef641a1bd241f070f7f90c9e632b375))
* update to use traefik route 0.4 ([39de118](https://github.com/canonical/kratos-operator/commit/39de118e699ee0458e31716efdede92afa3cb388))
* upgrade tf module to use 1.0.0 syntax ([709ed1b](https://github.com/canonical/kratos-operator/commit/709ed1b3f1a77432de073ac291f8d47b7c26ccae))
* use [external] ingress on login endpoint field of kratos info ([665fed1](https://github.com/canonical/kratos-operator/commit/665fed1c08a62f77d4582181bedb41f409c788e5))
* use config hash to restart service ([162382f](https://github.com/canonical/kratos-operator/commit/162382f62d4b9898a94fc776c8e96b8d58d8354f))
* use LogForwarder to send logs ([c76ebdc](https://github.com/canonical/kratos-operator/commit/c76ebdc7632869f281c0f20e4d75d5b8c57c20f8))
* use LogForwarder to send logs ([f548145](https://github.com/canonical/kratos-operator/commit/f5481450c8ebe2d6a821fb690c751bbe93756a25))
* use query param to fetch identity from email ([d272121](https://github.com/canonical/kratos-operator/commit/d272121e85f81e8c596f30086acff37baa89cf0b))
* use terraform module in deployment ([a6bdc44](https://github.com/canonical/kratos-operator/commit/a6bdc441e2339bcdfadfdb344ef77b85755e42f9))
* validate identity id ([592660f](https://github.com/canonical/kratos-operator/commit/592660fe205288d4a7497c094fe816c664611523))
* validate that identity id is a uuid ([8169232](https://github.com/canonical/kratos-operator/commit/8169232ed4df1098fbdc88b2f3a2ba3cf9020538))


### Code Refactoring

* refactor the charm ([ab286bf](https://github.com/canonical/kratos-operator/commit/ab286bf1491912571ec5e78d76d92e82999c807d))
* refactor the juju actions ([b92f779](https://github.com/canonical/kratos-operator/commit/b92f7792046d15e8925b5f5a9888fc547ead3224))
* use kratos external provider library v1 ([e3e9bc8](https://github.com/canonical/kratos-operator/commit/e3e9bc8a6974d5a30ca0ea915d75d22c11a9bf36))
