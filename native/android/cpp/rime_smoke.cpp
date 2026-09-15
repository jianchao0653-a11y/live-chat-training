#include <rime_api.h>
#include <cstdio>
#include <string>

int main(int argc, char** argv) {
  if (argc != 3) return 2;
  auto api = rime_get_api();
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = argv[1];
  traits.user_data_dir = argv[2];
  traits.app_name = "rime.lens.smoke";
  api->setup(&traits);
  api->initialize(&traits);
  if (api->start_maintenance(True)) api->join_maintenance_thread();
  auto session = api->create_session();
  if (!api->select_schema(session, "lens_pinyin")) return 3;
  const char* inputs[] = {"nihao", "zhongguo", "xiexie"};
  const char* expected[] = {"你好", "中国", "谢谢"};
  for (int i = 0; i < 3; ++i) {
    const char* input = inputs[i];
    api->clear_composition(session);
    for (const char* c = input; *c; ++c) api->process_key(session, *c, 0);
    RIME_STRUCT(RimeContext, context);
    if (!api->get_context(session, &context) || !context.menu.num_candidates) return 4;
    printf("%s -> %s\n", input, context.menu.candidates[0].text);
    api->free_context(&context);
    if (!api->select_candidate_on_current_page(session, 0)) return 5;
    RIME_STRUCT(RimeCommit, commit);
    if (!api->get_commit(session, &commit) || !commit.text || !*commit.text) return 6;
    if (std::string(commit.text) != expected[i]) {
      printf("Expected %s, received %s\n", expected[i], commit.text);
      return 7;
    }
    api->free_commit(&commit);
  }
  api->process_key(session, 'n', 0);
  api->process_key(session, 'i', 0);
  api->process_key(session, 0xff08, 0);
  if (std::string(api->get_input(session)) != "n") return 8;
  api->clear_composition(session);
  if (std::string(api->get_input(session)) != "") return 9;
  api->destroy_session(session);
  session = api->create_session();
  if (!api->select_schema(session, "lens_pinyin") || std::string(api->get_input(session)) != "") return 10;
  if (!api->select_schema(session, "lens_nine")) return 11;
  const char* digits[] = {"64426", "94664486", "943943"};
  for (int n = 0; n < 3; ++n) {
    api->clear_composition(session);
    for (const char* c = digits[n]; *c; ++c) api->process_key(session, *c, 0);
    bool selected = false;
    for (int page = 0; page < 20 && !selected; ++page) {
      RIME_STRUCT(RimeContext, ctx);
      if (!api->get_context(session, &ctx)) return 12;
      int match = -1;
      for (int i = 0; i < ctx.menu.num_candidates; ++i)
        if (std::string(ctx.menu.candidates[i].text) == expected[n]) match = i;
      bool last = ctx.menu.is_last_page;
      api->free_context(&ctx);
      if (match >= 0) { selected = api->select_candidate_on_current_page(session, match); break; }
      if (last || !api->change_page(session, False)) break;
    }
    if (!selected) { printf("Missing nine-key candidate: %s\n", digits[n]); return 13; }
    RIME_STRUCT(RimeCommit, result);
    if (!api->get_commit(session, &result)) return 14;
    bool correct = result.text && std::string(result.text) == expected[n];
    api->free_commit(&result);
    if (!correct) return 15;
    printf("nine %s -> expected candidate committed\n", digits[n]);
  }
  api->process_key(session, '6', 0);api->process_key(session, '4', 0);
  api->process_key(session, 0xff08, 0);
  if (std::string(api->get_input(session)) != "6") return 16;
  api->clear_composition(session);
  if (!api->select_schema(session, "lens_pinyin") || std::string(api->get_input(session)) != "") return 17;
  api->destroy_session(session);
  api->finalize();
  puts("RIME_SMOKE_PASS");
}
