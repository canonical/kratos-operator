# Changelog

## [2.0.0](https://github.com/canonical/kratos-operator/compare/v1.2.0...v2.0.0) (2025-11-17)


### ⚠ BREAKING CHANGES

* refactor the charm
* refactor the juju actions
* use kratos external provider library v1

### Features

* add actions to list identifiers and unlink account ([57e2c3c](https://github.com/canonical/kratos-operator/commit/57e2c3cd70d4f98d2e868b79076dd01f5ca1111f))
* add default return url for oidc settings ([6986ae7](https://github.com/canonical/kratos-operator/commit/6986ae763ad9e342dd7db30c0081c5f618fda8f8))
* drop ingresses in favour of traefik route ([c868490](https://github.com/canonical/kratos-operator/commit/c8684908fec871de0d8650ee9173b8224c002937))
* implement PublicRoute integration ([b4e91cd](https://github.com/canonical/kratos-operator/commit/b4e91cd2d99ed1a547cc6c52212d0bccd792077e))


### Bug Fixes

* add collect_status handler ([e441df6](https://github.com/canonical/kratos-operator/commit/e441df62e5133cba19cfe2433fa8d6b43c56cec2))
* add health check handlers ([355b8c0](https://github.com/canonical/kratos-operator/commit/355b8c0b648971890b6679b844520845e6f85a73))
* downgrade charm lib version ([0c392f3](https://github.com/canonical/kratos-operator/commit/0c392f38a2e3e6810793eda99a1e332bda9bb4bd))
* improve route integration handling logic ([c33d6c8](https://github.com/canonical/kratos-operator/commit/c33d6c865b98674d37166ed022414575aaa88d97))
* improve the error hint for create-admin-account juju action ([50166f8](https://github.com/canonical/kratos-operator/commit/50166f88f08a96850837c894b4c343445277117c))
* improve the error hint for create-admin-account juju action ([0d764cb](https://github.com/canonical/kratos-operator/commit/0d764cb2d7636b24b8fb395ad78f10c3d7639630))
* patch up internal-ingress and rename it internal-route ([79e02bf](https://github.com/canonical/kratos-operator/commit/79e02bf379f1b252abe5ef77870eabee4ecdaed2))
* stop service when database is gone ([a8d73cc](https://github.com/canonical/kratos-operator/commit/a8d73ccc28ac1288b2d75ebc253404b62daff16d))
* switch to use -route relations in the tf module ([a9c1087](https://github.com/canonical/kratos-operator/commit/a9c108729f7a3dde4b2169375aaab1dcc47c8cf4))
* update to use traefik route 0.4 ([39de118](https://github.com/canonical/kratos-operator/commit/39de118e699ee0458e31716efdede92afa3cb388))
* upgrade tf module to use 1.0.0 syntax ([709ed1b](https://github.com/canonical/kratos-operator/commit/709ed1b3f1a77432de073ac291f8d47b7c26ccae))


### Code Refactoring

* refactor the charm ([ab286bf](https://github.com/canonical/kratos-operator/commit/ab286bf1491912571ec5e78d76d92e82999c807d))
* refactor the juju actions ([b92f779](https://github.com/canonical/kratos-operator/commit/b92f7792046d15e8925b5f5a9888fc547ead3224))
* use kratos external provider library v1 ([e3e9bc8](https://github.com/canonical/kratos-operator/commit/e3e9bc8a6974d5a30ca0ea915d75d22c11a9bf36))

## [1.2.0](https://github.com/canonical/kratos-operator/compare/v1.1.11...v1.2.0) (2025-08-11)


### Features

* update juju_application resource name ([836e00f](https://github.com/canonical/kratos-operator/commit/836e00f63623f0e0524ac795ac62dd073cddaef5))


### Bug Fixes

* use terraform module in deployment ([a6bdc44](https://github.com/canonical/kratos-operator/commit/a6bdc441e2339bcdfadfdb344ef77b85755e42f9))

## [1.1.11](https://github.com/canonical/kratos-operator/compare/v1.1.10...v1.1.11) (2025-07-31)


### Bug Fixes

* update charm dependent libs ([d88c488](https://github.com/canonical/kratos-operator/commit/d88c488bf3e854f541387baec0a46fe6278c7ae2))
* use query param to fetch identity from email ([d272121](https://github.com/canonical/kratos-operator/commit/d272121e85f81e8c596f30086acff37baa89cf0b))

## [1.1.10](https://github.com/canonical/kratos-operator/compare/v1.1.9...v1.1.10) (2025-07-09)


### Bug Fixes

* check that relation is active ([56b4adc](https://github.com/canonical/kratos-operator/commit/56b4adc4228607f193db5ed162312f47ba61aec4))
* do not defer events if not needed ([2eca933](https://github.com/canonical/kratos-operator/commit/2eca9333f6ed28c8868b82e22345ea408e574540))

## [1.1.9](https://github.com/canonical/kratos-operator/compare/v1.1.8...v1.1.9) (2025-07-09)


### Bug Fixes

* compare config against cm ([94eb584](https://github.com/canonical/kratos-operator/commit/94eb5848ca98ef6611201b250f85a3bc372cf52f))
* restart service only when config changed ([259a15a](https://github.com/canonical/kratos-operator/commit/259a15af6f1ce3c36e0c9852bffe8aebc7910475))
* update run_after_config_updated ([fc8ad80](https://github.com/canonical/kratos-operator/commit/fc8ad802eef641a1bd241f070f7f90c9e632b375))
* use config hash to restart service ([162382f](https://github.com/canonical/kratos-operator/commit/162382f62d4b9898a94fc776c8e96b8d58d8354f))

## [1.1.8](https://github.com/canonical/kratos-operator/compare/v1.1.7...v1.1.8) (2025-07-01)


### Bug Fixes

* store api token in juju secret ([783228b](https://github.com/canonical/kratos-operator/commit/783228b0a479599706a33d96f380f2e3431e4436))

## [1.1.7](https://github.com/canonical/kratos-operator/compare/v1.1.6...v1.1.7) (2025-06-30)


### Bug Fixes

* align the idp k8s configmap key name ([c268413](https://github.com/canonical/kratos-operator/commit/c26841336ae9ee279fdcf28bb65684d7eaec42be))
* align the idp k8s configmap key name ([296da36](https://github.com/canonical/kratos-operator/commit/296da363f077a1cfbac339158b7ac280114a513d))
* validate identity id ([592660f](https://github.com/canonical/kratos-operator/commit/592660fe205288d4a7497c094fe816c664611523))
* validate that identity id is a uuid ([8169232](https://github.com/canonical/kratos-operator/commit/8169232ed4df1098fbdc88b2f3a2ba3cf9020538))

## [1.1.6](https://github.com/canonical/kratos-operator/compare/v1.1.5...v1.1.6) (2025-05-09)


### Bug Fixes

* fix constraint ([fc0b1be](https://github.com/canonical/kratos-operator/commit/fc0b1be120e0a241ad14f90f6649717aa3e56e20))

## [1.1.5](https://github.com/canonical/kratos-operator/compare/v1.1.4...v1.1.5) (2025-05-09)


### Bug Fixes

* add pod resource constraints ([d3807cb](https://github.com/canonical/kratos-operator/commit/d3807cbb91eca902dccb1fa9c4424829bb514ca9))

## [1.1.4](https://github.com/canonical/kratos-operator/compare/v1.1.3...v1.1.4) (2025-05-06)


### Bug Fixes

* fix auth config parsing ([bc74de1](https://github.com/canonical/kratos-operator/commit/bc74de1efb8a17791b3113a3b44efdb4e9ab7ba4))
* update all external-idp config in holistic handler ([8e517f5](https://github.com/canonical/kratos-operator/commit/8e517f50a2573f0f19c79091ae213619a9c95794))
* update charm dependent libs ([6f8c2df](https://github.com/canonical/kratos-operator/commit/6f8c2dfaeaeddd14ae2c6930e1865a552edb5770))

## [1.1.3](https://github.com/canonical/kratos-operator/compare/v1.1.2...v1.1.3) (2025-04-29)


### Bug Fixes

* check leadership ([300b10f](https://github.com/canonical/kratos-operator/commit/300b10f101fab7595fd0fe84e541b33f7718afbd))
* clean up webhook logic ([70be0b6](https://github.com/canonical/kratos-operator/commit/70be0b68025fb48ae441a5a286c30bd342017f84))
* explicitly disable unsupported methods ([e764823](https://github.com/canonical/kratos-operator/commit/e764823a4c89c0c3d534195573d4739c6762f9c0))
* explicitly disable unsupported methods ([7ebde0d](https://github.com/canonical/kratos-operator/commit/7ebde0da37a8447251f864665c57b5926d2dd4d3))
* fix the statefulset's name ([266f06d](https://github.com/canonical/kratos-operator/commit/266f06db554bb2fdf0b565dbdcc9166f5fe4907b))
* fix the statefulset's name ([10c0c52](https://github.com/canonical/kratos-operator/commit/10c0c52d6ae215ada5b7d75b59d8a47cff386fde))
* fix webhook auth ([5702f05](https://github.com/canonical/kratos-operator/commit/5702f0517a12e9f6116eb6c911e5fac3859e1628))

## [1.1.2](https://github.com/canonical/kratos-operator/compare/v1.1.1...v1.1.2) (2025-04-08)


### Bug Fixes

* add kratos_registration_webhook lib ([1f4d132](https://github.com/canonical/kratos-operator/commit/1f4d1321e5cf108a9243185c81f23745965163a5))
* bump ingress version ([313091f](https://github.com/canonical/kratos-operator/commit/313091f658e1dce535b0e954c116be074019a085))
* update login_ui lib, add registration_url ([b92f9f0](https://github.com/canonical/kratos-operator/commit/b92f9f0e608e3e3edd80cd0db9ff9786749436c0))

## [1.1.1](https://github.com/canonical/kratos-operator/compare/v1.1.0...v1.1.1) (2025-04-01)


### Bug Fixes

* address CVEs ([15b37f0](https://github.com/canonical/kratos-operator/commit/15b37f01f8a717f2003369a0302b1f34bafe6a50)), closes [#372](https://github.com/canonical/kratos-operator/issues/372)

## [1.1.0](https://github.com/canonical/kratos-operator/compare/v1.0.0...v1.1.0) (2025-03-26)


### Features

* add terraform module ([1a4eb77](https://github.com/canonical/kratos-operator/commit/1a4eb777575cf789cbaf772d5a1040db2d1073ea))
* add the terraform module ([241729a](https://github.com/canonical/kratos-operator/commit/241729a100da62eb78ab3763c2c318a923a576a6))


### Bug Fixes

* fix the lint ci ([c731894](https://github.com/canonical/kratos-operator/commit/c731894146f59c49c67583b7bebe4da5497954f0))
* fix the lint ci ([45b9d63](https://github.com/canonical/kratos-operator/commit/45b9d6319fe59a2914ceebd40741d316e13cc10c))
* provide optional flag in charmcraft.yaml ([fc0b664](https://github.com/canonical/kratos-operator/commit/fc0b6644a207ec0cdcfd567866d61982f16ecde1))
* skip CHANGELOG.md from spell check ([37042e1](https://github.com/canonical/kratos-operator/commit/37042e115f9b97fe788cafcfe0fe113478af4a64))
* skip CHANGELOG.md from spell check ([7ea81f9](https://github.com/canonical/kratos-operator/commit/7ea81f90386bae2b7e8633f301d6c425b5a130e8))

## 1.0.0 (2025-03-10)


### ⚠ BREAKING CHANGES

* remove the kratos-endpoint-info integration

### Features

* add account management actions ([82a3b06](https://github.com/canonical/kratos-operator/commit/82a3b06c5b87b63fe083d11f9b0a24f8501e77cb))
* add account management actions ([e9969c4](https://github.com/canonical/kratos-operator/commit/e9969c455666b7271aef11df5b9323075c4373a5))
* add enforce_mfa config option ([cdbbaa0](https://github.com/canonical/kratos-operator/commit/cdbbaa093e750cd126c093cd10458302d9893ab6))
* add is_ready check to kratos_info ([40e637b](https://github.com/canonical/kratos-operator/commit/40e637b8af041e119d9cde62d46aef08f4fc3413))
* add kratos_info interface ([b11e538](https://github.com/canonical/kratos-operator/commit/b11e538572bd4470db0bc5b7e48d6981a048e511))
* add proxy config variables ([8421de0](https://github.com/canonical/kratos-operator/commit/8421de06b749acb6eb55bbf6058a40ea9ffd1e77))
* add smtp integration ([2558093](https://github.com/canonical/kratos-operator/commit/2558093ca3ef207b837c821157f72f2c54283494))
* added alert rules to kratos ([17965be](https://github.com/canonical/kratos-operator/commit/17965be81e38f1708c2ba8a5e526dd6f9ef42452))
* added automerge and auto-approve to charm lib updates ([1ef3f7a](https://github.com/canonical/kratos-operator/commit/1ef3f7af309c9ad1dc14629a3dbc560717e62109))
* added base-channel parameter to release-charm action ([015406d](https://github.com/canonical/kratos-operator/commit/015406d2d9cac82c645acf69bb4ebdddc0c603b1))
* added grafana dashboard ([1d05ca8](https://github.com/canonical/kratos-operator/commit/1d05ca820539bbe54c31853a4b0ad9f7183e7652))
* added grafana-dashboard integration ([1d05ca8](https://github.com/canonical/kratos-operator/commit/1d05ca820539bbe54c31853a4b0ad9f7183e7652))
* bump kratos version to 1.0.0 ([e2074a7](https://github.com/canonical/kratos-operator/commit/e2074a7d975a5ce194494ffeb276fcdd54c477fd))
* enable tracing offer ([b25e243](https://github.com/canonical/kratos-operator/commit/b25e243dcfabffecd6bb5809672072d84f3632f2))
* inject proxy variables in the workload environment ([e1548df](https://github.com/canonical/kratos-operator/commit/e1548df48cd3d8f073c2dd5650527fa54258df1a))
* introduce internal ingress ([8fec05f](https://github.com/canonical/kratos-operator/commit/8fec05f76703b2075afa4d20068273d7fb642f9e))
* migrate to ingress v2 ([24af286](https://github.com/canonical/kratos-operator/commit/24af286971d0b4cd6e9a56d9bf858d239a4a4361))
* Move config to configMap ([cb76b28](https://github.com/canonical/kratos-operator/commit/cb76b2814d04fcf6babe21e64a145e23e2ed0e49))
* pass env vars to kratos for otlp http setup ([3b0e6e6](https://github.com/canonical/kratos-operator/commit/3b0e6e6af0754ef72dc26c4097833eeb01248a60))
* public ingress domain url is added to allowed return urls in the config if available ([8714f04](https://github.com/canonical/kratos-operator/commit/8714f04662c0add7205e6def8812b063ed7ad077))
* removed references to unused login-ui pages ([345b855](https://github.com/canonical/kratos-operator/commit/345b8554a339f5add0d24074b6cdf4c83afb537f))
* requirer side implementation of login_ui_endpoints interface  ([#49](https://github.com/canonical/kratos-operator/issues/49)) ([733685e](https://github.com/canonical/kratos-operator/commit/733685ed483335e0a655fdabd501c310e4c505c0))
* support backup codes ([2ec42d9](https://github.com/canonical/kratos-operator/commit/2ec42d9739532b51cdd9bfb8498005cc92dc0329))
* support backup codes if mfa enabled ([fb53017](https://github.com/canonical/kratos-operator/commit/fb53017f98683f56e878e237212567299b322e4d))
* support local identity provider ([f513e35](https://github.com/canonical/kratos-operator/commit/f513e354d6e246c94223661fb238d7be15c314b0))
* support local identity provider ([85474d8](https://github.com/canonical/kratos-operator/commit/85474d87a075ea41d7eb3da4a5291136c85e2195))
* support oidc webauthn sequencing mode ([dea7e4e](https://github.com/canonical/kratos-operator/commit/dea7e4e5315379e8c40133a1c6b064405522612d))
* support oidc webauthn sequencing mode ([b32d5ca](https://github.com/canonical/kratos-operator/commit/b32d5ca57215bfac18899f1f2f65937b8180ff81))
* updated hydra_endpoints relation name ([7713135](https://github.com/canonical/kratos-operator/commit/7713135d832e9b93954ef7fe81de63a1d8104ef7))
* updated login_ui_endpoints relation and associated unit tests ([cf00ecf](https://github.com/canonical/kratos-operator/commit/cf00ecf398f8f3e777ead3a4a63349ab52709dd3))
* updated tracing relation to tracing libpatch 6 ([99018ef](https://github.com/canonical/kratos-operator/commit/99018ef3d79b99851c1c9b283eb3beca0e694b5f))
* upgrade to v2 tracing ([c214a5c](https://github.com/canonical/kratos-operator/commit/c214a5cd0506b693eee40d748142fff136f35adb))
* use tracing v2 ([dfe3e5c](https://github.com/canonical/kratos-operator/commit/dfe3e5cdb578ae781dec7d52944d69587a19f60a))


### Bug Fixes

* add automerge enabled ([3121902](https://github.com/canonical/kratos-operator/commit/3121902328e291f4d38911f953361f71f55fa861))
* add github token to approver ([2d92838](https://github.com/canonical/kratos-operator/commit/2d9283833c835dbcd342f624e1b51c44181ceffa))
* add ory logo ([d74d2c0](https://github.com/canonical/kratos-operator/commit/d74d2c0e16e0bd592bb1875ebc974db594823f55))
* add tempo-k8s charm lib ([7d73701](https://github.com/canonical/kratos-operator/commit/7d73701d53ad5e2bd1d11258dd8a5d1d6b35bdc6))
* align actions to new cmd output format ([f78fb13](https://github.com/canonical/kratos-operator/commit/f78fb13b8a90df5fc0a88535c4df4c15ab4ab853))
* align actions to new cmd output format ([40a6844](https://github.com/canonical/kratos-operator/commit/40a68446a2b2248685736a922081eeee24d8b587))
* bump pytest-operator version ([10c0914](https://github.com/canonical/kratos-operator/commit/10c091488d21e7c9f82c08c8b7b424d96c26bb6c))
* bumped microk8s version to 1.28-strict/stable in CI ([eff91e4](https://github.com/canonical/kratos-operator/commit/eff91e40793178384214e67e77bc4c231492b77a))
* changed charm.py according to updates in login_ui_endpoints relation ([aac46ff](https://github.com/canonical/kratos-operator/commit/aac46ff09994b76181f03a9b07371a42240995c0))
* changed checkout action to v3 ([1ef3f7a](https://github.com/canonical/kratos-operator/commit/1ef3f7af309c9ad1dc14629a3dbc560717e62109))
* changed dashboard to fit kratos use case ([61bcde5](https://github.com/canonical/kratos-operator/commit/61bcde55bc0888a34aff787a912b5c58e3bae5ca))
* cleanup resources when charm is removed ([64a2eb3](https://github.com/canonical/kratos-operator/commit/64a2eb3f567ba2a1fbe8eb1199bb1a7878570862))
* do not produce wrong config ([0dd8c93](https://github.com/canonical/kratos-operator/commit/0dd8c938571314195295bd0d58961a0a171d50ef))
* embed claim mappers in confing map ([bcbf395](https://github.com/canonical/kratos-operator/commit/bcbf395fa1540a38eb6ce575868f578db967b837))
* enable auto-merge ([77e20b7](https://github.com/canonical/kratos-operator/commit/77e20b7d1073f97d5afa8b5c9b80447734ffee69))
* expose app version to juju ([a053d52](https://github.com/canonical/kratos-operator/commit/a053d5262b90b47d0a933b30657791c5cdd1900c)), closes [#160](https://github.com/canonical/kratos-operator/issues/160)
* fix bug in auto-approver ([1ef3f7a](https://github.com/canonical/kratos-operator/commit/1ef3f7af309c9ad1dc14629a3dbc560717e62109))
* fix default config if there is no secret ([e7e8923](https://github.com/canonical/kratos-operator/commit/e7e8923dd03a99f27b352020b06a053ca63e9b4a))
* fix integration with admin UI ([2518433](https://github.com/canonical/kratos-operator/commit/25184339be6b4a828228bb322271d0de8cdbd5e9))
* fix password input definition ([2ee2922](https://github.com/canonical/kratos-operator/commit/2ee29229954ae96b6b5c239b7db4774fb0d91638))
* fix the run-migration action failing condition issue ([4aa80ff](https://github.com/canonical/kratos-operator/commit/4aa80fff15f0227fb5b40126c3a22ab6c4821365))
* fix the run-migration action failing condition issue ([683ca9b](https://github.com/canonical/kratos-operator/commit/683ca9bdc119f6d15cffe2b2f12fc0605606fd2f))
* fixed alert logs ([d4fdd63](https://github.com/canonical/kratos-operator/commit/d4fdd639d2f1e9ef9a4669a5f79bacd86770d610))
* fixed dashboard ([d57827f](https://github.com/canonical/kratos-operator/commit/d57827f2439f68cb48f2ef3e81f11bc692e68aa0))
* fixed formating and linting in src/utils.py ([8714f04](https://github.com/canonical/kratos-operator/commit/8714f04662c0add7205e6def8812b063ed7ad077))
* fixed formating in src/charm.py ([8714f04](https://github.com/canonical/kratos-operator/commit/8714f04662c0add7205e6def8812b063ed7ad077))
* fixed grafana dashboard ([91363fe](https://github.com/canonical/kratos-operator/commit/91363fe992d91ee63c181837878f4dee16782580))
* fixed issue around the log file directory ([#80](https://github.com/canonical/kratos-operator/issues/80)) ([506c165](https://github.com/canonical/kratos-operator/commit/506c165dedf7163fe4c4e1dc63fc3946b0fa5e3a))
* fixed issue with login_ui_endpoints relation ([7ee4f07](https://github.com/canonical/kratos-operator/commit/7ee4f0727319f0e895427a469c075bdaaa7a3d33))
* fixed linting ([fb58a99](https://github.com/canonical/kratos-operator/commit/fb58a991d2025f67f55ee42e9d4ce71a1e0c46f2))
* fixed loki alert rule ([3f35c21](https://github.com/canonical/kratos-operator/commit/3f35c21e64bee72cbb4f85cd8fd3a3f43c5fa1cc))
* fixed loki alert rule ([ac815cb](https://github.com/canonical/kratos-operator/commit/ac815cb33984010956d8d2b70502d1558bec437b))
* fixed registration configuration ([7ee4f07](https://github.com/canonical/kratos-operator/commit/7ee4f0727319f0e895427a469c075bdaaa7a3d33))
* handle database relation departed ([84a8f2d](https://github.com/canonical/kratos-operator/commit/84a8f2dc441afec6f7623ae941d17fa74322cf4e)), closes [#166](https://github.com/canonical/kratos-operator/issues/166)
* handle database removal ([66ee72f](https://github.com/canonical/kratos-operator/commit/66ee72f16bc4a43e98ed77f0ff1ca3db02d28892))
* hardcode relation in constants.py ([72f41fa](https://github.com/canonical/kratos-operator/commit/72f41fad5561720954152a2c9a0c627c754e7d10))
* hardcode relation in constants.py ([6dd8798](https://github.com/canonical/kratos-operator/commit/6dd8798fe5512b9e57366b27c6e4422ceb173b67))
* improve migration logic ([d790569](https://github.com/canonical/kratos-operator/commit/d790569be13ec855182b5e9c2351186308ecdec6))
* introduce certificate transfer integration ([a4138d1](https://github.com/canonical/kratos-operator/commit/a4138d1ac009f9678c75df036e3019b7d2c38161))
* invalid config when no OIDC Provider ([b2b43b9](https://github.com/canonical/kratos-operator/commit/b2b43b964197d86c776fea4c3e3d69b00a7c61cc)), closes [#157](https://github.com/canonical/kratos-operator/issues/157)
* json dump contents to peer relation ([5dc9a81](https://github.com/canonical/kratos-operator/commit/5dc9a815d88ca1545e65646c1a83b6865c3df5db))
* Kratos fails to restart when cluster reboots ([#89](https://github.com/canonical/kratos-operator/issues/89)) ([b54a33c](https://github.com/canonical/kratos-operator/commit/b54a33ca0b10836494dddafc1925b7cdda33ecb3))
* load/dump json to cm ([a0d9138](https://github.com/canonical/kratos-operator/commit/a0d91381093ed3a97e90848635de8e1ed71a69e0)), closes [#252](https://github.com/canonical/kratos-operator/issues/252)
* **loki-rule:** improve error handling in json parsing ([b1b4cf9](https://github.com/canonical/kratos-operator/commit/b1b4cf9035eaeacc99804bd36d12fbc5d7f7cfae))
* **loki-rule:** improve error handling in json parsing ([6ca4f19](https://github.com/canonical/kratos-operator/commit/6ca4f194ebcdb5b2e7a8b1a6096b845f56330264))
* move charm constants to separate file ([3936553](https://github.com/canonical/kratos-operator/commit/39365539141c34e9a0df421574d6066c6e27c8b9)), closes [#90](https://github.com/canonical/kratos-operator/issues/90)
* Move configMap handling to separate class ([2ff3373](https://github.com/canonical/kratos-operator/commit/2ff33730adeb52681164bbb5390e9e2e428ef852))
* move dsn and base_url to env vars ([d49b855](https://github.com/canonical/kratos-operator/commit/d49b8555f3deb97d83bb37097ed50b4d9d7588e0))
* pin integration test requirements ([66b5e5e](https://github.com/canonical/kratos-operator/commit/66b5e5e0cb87ef9b2defd72721cb347c88f1412b))
* raise error if kratos info relation data is None ([c9865e6](https://github.com/canonical/kratos-operator/commit/c9865e6b4366c3ecb4dd4d1ee023763021e56d6e))
* rebased branch ([1ef3f7a](https://github.com/canonical/kratos-operator/commit/1ef3f7af309c9ad1dc14629a3dbc560717e62109))
* refactored code in _render_conf_file ([8714f04](https://github.com/canonical/kratos-operator/commit/8714f04662c0add7205e6def8812b063ed7ad077))
* remove `*` from allowed_urls ([6bc8d3d](https://github.com/canonical/kratos-operator/commit/6bc8d3df783b3e886e8886261090b61e40967fbe))
* remove renovate workflow ([603ebfb](https://github.com/canonical/kratos-operator/commit/603ebfbe2e6b3c431c69a8ebea82d503534c7450))
* remove the kratos-endpoint-info integration ([f3db749](https://github.com/canonical/kratos-operator/commit/f3db749198e0fe75dc270e495af51b9d7200ebfc))
* removed mappers_path from config template rendering in _render_conf_file ([8714f04](https://github.com/canonical/kratos-operator/commit/8714f04662c0add7205e6def8812b063ed7ad077))
* removed redundant urls from allowed return url in config ([8714f04](https://github.com/canonical/kratos-operator/commit/8714f04662c0add7205e6def8812b063ed7ad077))
* switch to tenacity package ([af8ab44](https://github.com/canonical/kratos-operator/commit/af8ab4484bedaea40797bc0751927599eb2f01d8))
* test names ([46a7da1](https://github.com/canonical/kratos-operator/commit/46a7da1d726d440b96e57377ecaf52c969e16c46))
* tracing relation update ([8950a95](https://github.com/canonical/kratos-operator/commit/8950a95815eec3e6640b463d9ec857adbed55885))
* tracing relation update ([deb4fe6](https://github.com/canonical/kratos-operator/commit/deb4fe6e15b2f2fad13f76c161d3706c91a3e921))
* **unit tests:** fixed broken CI run tests after ops dependency update ([05984ec](https://github.com/canonical/kratos-operator/commit/05984ecda8750aa84a698b660ba23c219316c318))
* unpin macaroonbakery ([d5ff92b](https://github.com/canonical/kratos-operator/commit/d5ff92bcd4289c53e82b1cd9e4455e05784455fb))
* update alert rules ([4f1120e](https://github.com/canonical/kratos-operator/commit/4f1120edb2f5d50c3b7fe9967af1d450d960e637))
* update grafana dashboards ([754d3e3](https://github.com/canonical/kratos-operator/commit/754d3e39ce372725d03b792e1e1ff22dda4a6e55))
* update kratos_external_idp_integrator lib ([66b6a0f](https://github.com/canonical/kratos-operator/commit/66b6a0fef1ffc7e5f45939a286aa6b8bf254cfc5))
* update lib version ([6b16b29](https://github.com/canonical/kratos-operator/commit/6b16b29a110204c92a94727146faa8146b84ce4d))
* updated actions/checkout to v4 ([1ef3f7a](https://github.com/canonical/kratos-operator/commit/1ef3f7af309c9ad1dc14629a3dbc560717e62109))
* updated login_ui_endpoints lib ([345b855](https://github.com/canonical/kratos-operator/commit/345b8554a339f5add0d24074b6cdf4c83afb537f))
* updated login_ui_endpoints relation ([a9808ad](https://github.com/canonical/kratos-operator/commit/a9808ada3dfb01145c3032c6063d82bf3516e5ab))
* updated unit tests ([345b855](https://github.com/canonical/kratos-operator/commit/345b8554a339f5add0d24074b6cdf4c83afb537f))
* use _handle_status_update_config to start charm ([a262241](https://github.com/canonical/kratos-operator/commit/a262241b35720a6865932701a6e204fd54ea9fc5))
* use [external] ingress on login endpoint field of kratos info ([665fed1](https://github.com/canonical/kratos-operator/commit/665fed1c08a62f77d4582181bedb41f409c788e5))
* use [external] ingress on login endpoint field of kratos info ([9f134b8](https://github.com/canonical/kratos-operator/commit/9f134b8cbd351277b303cb34b9b5cdea542f4565)), closes [#267](https://github.com/canonical/kratos-operator/issues/267)
* Use DSN to run migration ([13cbaec](https://github.com/canonical/kratos-operator/commit/13cbaec7d2cdb7fb70cf71f96578f3d59c11d476))
* use http endpoint in kratos-endpoint-info integration ([d777ae1](https://github.com/canonical/kratos-operator/commit/d777ae1fe4aae1862d17b577c7e37ea1c4e59e18))
* use http endpoint in kratos-endpoint-info integration ([f6b9d0c](https://github.com/canonical/kratos-operator/commit/f6b9d0cffd58a3a475d995c1844e328735ee2f7f))
* use internal ingress if set, otherwise stick with k8s networking ([e44716a](https://github.com/canonical/kratos-operator/commit/e44716aa8522d1b99a76836b2d612fb15a0eaff8))
* use LogForwarder to send logs ([c76ebdc](https://github.com/canonical/kratos-operator/commit/c76ebdc7632869f281c0f20e4d75d5b8c57c20f8))
* use LogForwarder to send logs ([f548145](https://github.com/canonical/kratos-operator/commit/f5481450c8ebe2d6a821fb690c751bbe93756a25))
* use RENOVATE_TOKEN env var ([809b882](https://github.com/canonical/kratos-operator/commit/809b882c9cebcbb4fe86ba4d068a001a9fd1041d))
* wait for configmap changes to apply ([0f11ece](https://github.com/canonical/kratos-operator/commit/0f11ece0f4842bbac92ef9156ebff1c647fb275b))
