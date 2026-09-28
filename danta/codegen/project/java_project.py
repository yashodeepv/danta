"""java_project.py - A system -> a Spring Boot 3 project (Java 17, Maven).

    <system>/
      pom.xml   README.md
      src/main/java/<pkg>/
        Application.java          @SpringBootApplication, scheduling on
        runtime/R.java            results, service calls, 32-bit arithmetic
        Models.java               records for entities, flow inputs, service contracts
        ports/                    one typed interface per service; ServiceRouter routes flow calls to them
        adapters/                 @Component stand-ins: in-memory store, logging notifier, fake services
        flows/                    one @Service per flow; the logic itself is plain Java
        web/FlowController.java   @RestController: one endpoint per HTTP trigger
        events/                   FlowEvent, and an @EventListener per event trigger
        schedule/ScheduledFlows   @Scheduled per schedule trigger
      src/main/resources/application.properties
      src/test/java/<pkg>/        JUnit 5: every scenario per flow, plus a Spring context + HTTP test
      src/test/resources/scenarios/<flow>.json

Replacing a stand-in is ordinary Spring: declare your own bean of the port's
type and mark it @Primary (or remove the fake).
"""

import json
import re

from danta.codegen.java import RUNTIME_BODY, flow_method
from danta.codegen.openapi import asyncapi, openapi
from danta.codegen.project import deploy, frontend, infra

JAVA_DOCKERFILE = """
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/target/*.jar app.jar
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
"""
from danta.codegen.project.common import camel, collect_types, data_entities, fake_outputs, outline, snake, trigger_line
from danta.ir2.types import BOOL, INT, STR, ListT, RecordT

SPRING_BOOT = '3.5.0'
SPRINGDOC = '2.8.9'

JAVA_RESERVED = {'abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch', 'char', 'class', 'const',
                 'continue', 'default', 'do', 'double', 'else', 'enum', 'extends', 'final', 'finally', 'float',
                 'for', 'goto', 'if', 'implements', 'import', 'instanceof', 'int', 'interface', 'long', 'native',
                 'new', 'package', 'private', 'protected', 'public', 'return', 'short', 'static', 'strictfp',
                 'super', 'switch', 'synchronized', 'this', 'throw', 'throws', 'transient', 'try', 'void',
                 'volatile', 'while', 'true', 'false', 'null', 'var', 'record', 'yield'}

# The runtime without its JSON section: Spring brings Jackson.
RUNTIME = RUNTIME_BODY.split('    // ---- JSON')[0].rstrip() + '\n'


def ident(name):
    return name + '_' if name in JAVA_RESERVED else name


def lower_camel(name):
    c = camel(name)
    return ident(c[:1].lower() + c[1:])


def jstr(s):
    return json.dumps(s)


def jtype(t, namer, boxed=False):
    if t == INT:
        return 'Integer' if boxed else 'int'
    if t == STR:
        return 'String'
    if t == BOOL:
        return 'Boolean' if boxed else 'boolean'
    if isinstance(t, ListT):
        return f'List<{jtype(t.elem, namer, True)}>'
    return f'Models.{namer.names[t]}'


def from_obj(t, code, namer, depth=0):
    if t == INT:
        return f'((Number) {code}).intValue()'
    if t == STR:
        return f'((String) {code})'
    if t == BOOL:
        return f'((Boolean) {code})'
    if isinstance(t, ListT):
        x = f'x{depth}'
        return (f'R.asList({code}).stream().map({x} -> {from_obj(t.elem, x, namer, depth + 1)})'
                f'.collect(Collectors.toList())')
    return f'Models.{namer.names[t]}.fromMap(R.asMap({code}))'


def to_obj(t, code, depth=0):
    if isinstance(t, ListT):
        x = f'x{depth}'
        return f'{code}.stream().map({x} -> (Object) {to_obj(t.elem, x, depth + 1)}).collect(Collectors.toList())'
    if isinstance(t, RecordT):
        return f'{code}.toMap()'
    return code


def default(t, namer):
    if t == INT:
        return '0'
    if t == STR:
        return '""'
    if t == BOOL:
        return 'false'
    if isinstance(t, ListT):
        return 'new ArrayList<>()'
    return f'new Models.{namer.names[t]}(' + ', '.join(default(ft, namer) for _, ft in t.fields) + ')'


def literal(t, v, namer):
    """A Java expression for value v of IR2 type t."""
    if t == INT:
        return str(int(v))
    if t == STR:
        return jstr(str(v))
    if t == BOOL:
        return 'true' if v else 'false'
    if isinstance(t, ListT):
        return f'new ArrayList<>(List.of({", ".join(literal(t.elem, x, namer) for x in v)}))' if v else 'new ArrayList<>()'
    return f'new Models.{namer.names[t]}(' + ', '.join(literal(ft, v.get(n), namer) for n, ft in t.fields) + ')'


def spring_cron(cron):
    """Unix 5-field cron -> Spring's 6-field cron (seconds first)."""
    return '0 ' + ' '.join(cron.split())


# --------------------------------------------------------------------------
# main sources
# --------------------------------------------------------------------------

def _models(pkg, namer):
    out = [f'package {pkg};', '', 'import java.util.*;', 'import java.util.stream.Collectors;',
           f'import {pkg}.runtime.R;', '',
           '/** Data shapes: entities, flow inputs and service contracts. Flows exchange them as maps',
           ' *  (the JSON shape); fromMap/toMap convert. */', 'public final class Models {', 'private Models() {}']
    for name, rec in namer.defs:
        comps = ', '.join(f'{jtype(t, namer)} {ident(n)}' for n, t in rec.fields)
        out += [f'public record {name}({comps}) {{',
                f'public static {name} fromMap(Map<String, Object> m) {{',
                f'return new {name}(' + ', '.join(from_obj(t, f'm.get({jstr(n)})', namer) for n, t in rec.fields) + ');',
                '}',
                'public Map<String, Object> toMap() {',
                'Map<String, Object> m = new LinkedHashMap<>();']
        out += [f'm.put({jstr(n)}, {to_obj(t, ident(n))});' for n, t in rec.fields]
        out += ['return m;', '}', '}']
    out.append('}')
    return '\n'.join(out) + '\n'


def _ports(pkg, system, namer):
    files = {}
    for s, ops in sorted(system.services.items()):
        lines = [f'package {pkg}.ports;', '', 'import java.util.*;', f'import {pkg}.Models;',
                 f'import {pkg}.runtime.R;', '',
                 f'/** The {s} service. Throw R.ServiceError when a call fails. Provide your own',
                 ' *  implementation as a Spring bean (mark it @Primary to replace the fake). */',
                 f'public interface {camel(s)} {{']
        for op, sig in ops.items():
            params = ', '.join(f'{jtype(t, namer)} {ident(n)}' for n, t in sig.input.fields)
            lines.append(f'{jtype(sig.output, namer)} {ident(op)}({params}) throws R.ServiceError;')
        lines.append('}')
        files[f'ports/{camel(s)}.java'] = '\n'.join(lines) + '\n'

    svcs = sorted(system.services)
    fields = '\n'.join(f'private final {camel(s)} {ident(s)};' for s in svcs)
    params = ', '.join(f'{camel(s)} {ident(s)}' for s in svcs)
    assigns = '\n'.join(f'this.{ident(s)} = {ident(s)};' for s in svcs)
    cases = []
    for s in svcs:
        for op, sig in system.services[s].items():
            args = ', '.join(from_obj(t, f'args.get({jstr(n)})', namer) for n, t in sig.input.fields)
            cases.append(f'case {jstr(s + "." + op)}: return {ident(s)}.{ident(op)}({args}).toMap();')
    files['ports/ServiceRouter.java'] = f'''package {pkg}.ports;

import java.util.*;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;
import {pkg}.Models;
import {pkg}.runtime.R;

/** Routes the flows' service calls to the service beans. */
@Component
public class ServiceRouter implements R.Services {{
{fields}

public ServiceRouter({params}) {{
{assigns}
}}

@Override
public Map<String, Object> call(String service, String op, Map<String, Object> args, String step) throws R.ServiceError {{
switch (service + "." + op) {{
{chr(10).join(cases)}
default: throw new R.ServiceError("unknown operation " + service + "." + op);
}}
}}
}}
'''
    return files


def _adapters(pkg, system, namer):
    keys = ', '.join(f'Map.entry({jstr(e)}, {jstr(rec.fields[0][0])})' for e, rec in system.entities.items())
    files = {
        'adapters/InMemoryStore.java': f'''package {pkg}.adapters;

import java.util.*;
import org.springframework.stereotype.Component;
import {pkg}.runtime.R;

/** Keeps records in memory, one list per entity. Replace with a @Primary R.Store / R.Query bean for a real database. */
@Component
public class InMemoryStore implements R.Store, R.Query {{
private static final Map<String, String> KEYS = Map.ofEntries({keys});

public final Map<String, List<Map<String, Object>>> records = new HashMap<>();

@Override
public synchronized void store(String entity, String op, Map<String, Object> data) {{
List<Map<String, Object>> rows = records.computeIfAbsent(entity, k -> new ArrayList<>());
String key = KEYS.get(entity);
if (op.equals("create")) {{
rows.add(new LinkedHashMap<>(data));
return;
}}
rows.removeIf(r -> Objects.equals(r.get(key), data.get(key)));
if (op.equals("update")) rows.add(new LinkedHashMap<>(data));
}}

@Override
public synchronized List<Object> query(String entity, Map<String, Object> where) {{
List<Object> found = new ArrayList<>();
for (Map<String, Object> r : records.getOrDefault(entity, List.of())) {{
boolean all = where.entrySet().stream().allMatch(w -> Objects.equals(r.get(w.getKey()), w.getValue()));
if (all) found.add(new LinkedHashMap<>(r));
}}
return found;
}}
}}
''',
        'adapters/TopicPublisher.java': f'''package {pkg}.adapters;

import java.util.Map;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import {pkg}.events.TopicMessage;
import {pkg}.runtime.R;

/** Publishes to topics in-process, as Spring application events. Replace with a @Primary
 *  R.Publisher bean to use a real broker. */
@Component
public class TopicPublisher implements R.Publisher {{
private final ApplicationEventPublisher events;

public TopicPublisher(ApplicationEventPublisher events) {{
this.events = events;
}}

@Override
public void publish(String topic, Map<String, Object> message) {{
events.publishEvent(new TopicMessage(topic, message));
}}
}}
''',
        'adapters/LoggingNotifier.java': f'''package {pkg}.adapters;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import {pkg}.runtime.R;

/** Logs messages instead of sending them. Replace with a @Primary R.Notifier bean. */
@Component
public class LoggingNotifier implements R.Notifier {{
private static final Logger log = LoggerFactory.getLogger(LoggingNotifier.class);

@Override
public void notify(String channel, String to, String message) {{
log.info("[{{}} -> {{}}] {{}}", channel, to, message);
}}
}}
''',
    }
    values = fake_outputs(system)
    for s, ops in sorted(system.services.items()):
        methods = []
        for op, sig in ops.items():
            params = ', '.join(f'{jtype(t, namer)} {ident(n)}' for n, t in sig.input.fields)
            methods.append(f'@Override\npublic {jtype(sig.output, namer)} {ident(op)}({params}) {{\n'
                           f'return {literal(sig.output, values[(s, op)], namer)};\n}}')
        files[f'adapters/Fake{camel(s)}.java'] = f'''package {pkg}.adapters;

import java.util.*;
import org.springframework.stereotype.Component;
import {pkg}.Models;
import {pkg}.ports.{camel(s)};

/** Stands in for the {s} service: always succeeds, with the values of the passing test run. */
@Component
public class Fake{camel(s)} implements {camel(s)} {{
{chr(10).join(methods)}
}}
'''
    return files


def _real_adapters(pkg, system):
    """@Primary beans for real infrastructure, switched on by the same environment variables
    as the other languages (STORE, BROKER, NOTIFY, ADMIN_API)."""
    topics = [f for f in system.flows if f.trigger().source == 'topic']
    keys = ', '.join(f'Map.entry({jstr(e)}, {jstr(rec.fields[0][0])})' for e, rec in system.entities.items())
    files = {
        'adapters/MongoStore.java': f"""package {pkg}.adapters;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import java.util.*;
import org.bson.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;
import {pkg}.runtime.R;

/** Records in MongoDB (STORE=mongo), one collection per entity. Updates and deletes match the
 *  entity's key field; queries return records in the order they were stored. */
@Component
@Primary
@ConditionalOnProperty(name = "store", havingValue = "mongo")
public class MongoStore implements R.Store, R.Query {{
private static final Map<String, String> KEYS = Map.ofEntries({keys});
private final MongoDatabase db;

public MongoStore(@Value("${{MONGO_URL:mongodb://localhost:27017}}") String url, @Value("${{MONGO_DB:{snake(system.name)}}}") String database) {{
MongoClient client = MongoClients.create(url);
this.db = client.getDatabase(database);
}}

@Override
public void store(String entity, String op, Map<String, Object> data) {{
String key = KEYS.get(entity);
if (!op.equals("create")) db.getCollection(entity).deleteMany(Filters.eq(key, data.get(key)));
if (!op.equals("delete")) db.getCollection(entity).insertOne(new Document(data));
}}

@Override
public List<Object> query(String entity, Map<String, Object> where) {{
List<Object> out = new ArrayList<>();
for (Document d : db.getCollection(entity).find(new Document(where)).sort(Sorts.ascending("_id"))) {{
Map<String, Object> row = new LinkedHashMap<>(d);
row.remove("_id");
out.add(row);
}}
return out;
}}
}}
""",
        'adapters/RabbitTopics.java': f"""package {pkg}.adapters;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;
import {pkg}.runtime.R;

/** Topics on a RabbitMQ topic exchange (BROKER=rabbitmq). Each subscribed flow has its own durable
 *  queue (see TopicConsumers), so every flow gets every message and instances share the work. */
@Component
@Primary
@ConditionalOnProperty(name = "broker", havingValue = "rabbitmq")
public class RabbitTopics implements R.Publisher {{
public static final String EXCHANGE = "flows";
private static final ObjectMapper JSON = new ObjectMapper();
public final CachingConnectionFactory connections;
public final RabbitAdmin admin;
private final RabbitTemplate template;

public RabbitTopics(@Value("${{RABBITMQ_URL:amqp://guest:guest@localhost:5672}}") String url) {{
connections = new CachingConnectionFactory(java.net.URI.create(url));
admin = new RabbitAdmin(connections);
// the broker may still be starting (docker compose, Kubernetes): retry for a minute, like the other languages
for (int attempt = 1; ; attempt++) {{
try {{
admin.declareExchange(new TopicExchange(EXCHANGE, true, false));
break;
}} catch (org.springframework.amqp.AmqpException e) {{
if (attempt == 30) {{
throw e;
}}
try {{
Thread.sleep(2000);
}} catch (InterruptedException ie) {{
Thread.currentThread().interrupt();
throw e;
}}
}}
}}
template = new RabbitTemplate(connections);
}}

@Override
public void publish(String topic, Map<String, Object> message) {{
try {{
MessageProperties props = new MessageProperties();
props.setContentType("application/json");
template.send(EXCHANGE, topic, new org.springframework.amqp.core.Message(JSON.writeValueAsBytes(message), props));
}} catch (Exception e) {{
throw new IllegalStateException("could not publish to " + topic, e);
}}
}}
}}
""",
        'adapters/SmtpNotifier.java': f"""package {pkg}.adapters;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;
import {pkg}.runtime.R;

/**
 * Sends email over SMTP (NOTIFY=smtp; Mailpit catches it locally); other channels are logged. With
 * SMTP_USER and SMTP_PASSWORD (a real relay) it upgrades to TLS and logs in.
 */
@Component
@Primary
@ConditionalOnProperty(name = "notify", havingValue = "smtp")
public class SmtpNotifier implements R.Notifier {{
private static final Logger log = LoggerFactory.getLogger(SmtpNotifier.class);
private final JavaMailSenderImpl mail = new JavaMailSenderImpl();
private final String from;

public SmtpNotifier(@Value("${{SMTP_HOST:localhost}}") String host, @Value("${{SMTP_PORT:1025}}") int port,
@Value("${{SMTP_FROM:{system.name}@example.com}}") String from,
@Value("${{SMTP_USER:}}") String user, @Value("${{SMTP_PASSWORD:}}") String password) {{
mail.setHost(host);
mail.setPort(port);
if (!user.isEmpty()) {{
mail.setUsername(user);
mail.setPassword(password);
mail.getJavaMailProperties().put("mail.smtp.auth", "true");
mail.getJavaMailProperties().put("mail.smtp.starttls.enable", "true");
mail.getJavaMailProperties().put("mail.smtp.starttls.required", "true");
}}
this.from = from;
}}

@Override
public void notify(String channel, String to, String message) {{
if (!channel.equals("email")) {{
log.info("[{{}} -> {{}}] {{}}", channel, to, message);
return;
}}
SimpleMailMessage m = new SimpleMailMessage();
m.setFrom(from);
m.setTo(to);
m.setSubject(message.length() > 78 ? message.substring(0, 78) : message);
m.setText(message);
mail.send(m);
}}
}}
""",
    }
    if topics:
        fields = '\n'.join(f'private final {camel(f.name)}Flow {lower_camel(f.name)};' for f in topics)
        params = ', '.join(f'{camel(f.name)}Flow {lower_camel(f.name)}' for f in topics)
        assigns = '\n'.join(f'this.{lower_camel(f.name)} = {lower_camel(f.name)};' for f in topics)
        listen = '\n'.join(f'listen({jstr(f.trigger().config["name"])}, {jstr(f.name)}, {lower_camel(f.name)}::run);'
                           for f in topics)
        imports = '\n'.join(f'import {pkg}.flows.{camel(f.name)}Flow;' for f in topics)
        files['adapters/TopicConsumers.java'] = f"""package {pkg}.adapters;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.MessageListener;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
{imports}

/** Consumes the subscribed topics from RabbitMQ (BROKER=rabbitmq): one durable queue per flow. */
@Component
@ConditionalOnProperty(name = "broker", havingValue = "rabbitmq")
public class TopicConsumers {{
private static final Logger log = LoggerFactory.getLogger(TopicConsumers.class);
private static final ObjectMapper JSON = new ObjectMapper();
private final RabbitTopics topics;
private final List<SimpleMessageListenerContainer> containers = new ArrayList<>();
{fields}

public TopicConsumers(RabbitTopics topics, {params}) {{
this.topics = topics;
{assigns}
}}

@PostConstruct
void start() {{
{listen}
}}

@PreDestroy
void stop() {{
containers.forEach(SimpleMessageListenerContainer::stop);
}}

@SuppressWarnings("unchecked")
private void listen(String topic, String flow, Function<Map<String, Object>, Map<String, Object>> run) {{
String queue = "{system.name}." + flow;
topics.admin.declareQueue(new Queue(queue, true));
topics.admin.declareBinding(BindingBuilder.bind(new Queue(queue, true)).to(new TopicExchange(RabbitTopics.EXCHANGE, true, false)).with(topic));
SimpleMessageListenerContainer c = new SimpleMessageListenerContainer(topics.connections);
c.setQueueNames(queue);
c.setPrefetchCount(1);
c.setMessageListener((MessageListener) m -> {{
try {{
run.apply(new LinkedHashMap<>(JSON.readValue(m.getBody(), Map.class)));
}} catch (Exception e) {{
log.error("flow {{}} failed on a message", flow, e);
}}
}});
c.start();
containers.add(c);
}}
}}
"""
    runs = '\n'.join(f'case {jstr(f.name)}: return {lower_camel(f.name)}.run(request);' for f in system.flows)
    fields = '\n'.join(f'private final {camel(f.name)}Flow {lower_camel(f.name)};' for f in system.flows)
    params = ', '.join(f'{camel(f.name)}Flow {lower_camel(f.name)}' for f in system.flows)
    assigns = '\n'.join(f'this.{lower_camel(f.name)} = {lower_camel(f.name)};' for f in system.flows)
    imports = '\n'.join(f'import {pkg}.flows.{camel(f.name)}Flow;' for f in system.flows)
    files['web/AdminController.java'] = f"""package {pkg}.web;

import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import {pkg}.runtime.R;
{imports}

/** Local testing only (ADMIN_API=1): run any flow, and read or seed records. */
@RestController
@RequestMapping("/admin")
@ConditionalOnProperty(name = "admin.api", havingValue = "1")
public class AdminController {{
private final R.Store store;
private final R.Query query;
{fields}

public AdminController(R.Store store, R.Query query, {params}) {{
this.store = store;
this.query = query;
{assigns}
}}

@PostMapping("/flows/{{name}}")
public ResponseEntity<Object> run(@PathVariable String name, @RequestBody(required = false) Map<String, Object> body) {{
Map<String, Object> result = dispatch(name, body == null ? new LinkedHashMap<>() : body);
return result == null ? ResponseEntity.notFound().build() : ResponseEntity.ok(result);
}}

@GetMapping("/store/{{entity}}")
public List<Object> records(@PathVariable String entity) {{
return query.query(entity, Map.of());
}}

@PostMapping("/store/{{entity}}")
public Map<String, Object> seed(@PathVariable String entity, @RequestBody Map<String, Object> body) {{
store.store(entity, "create", body);
return Map.of("created", true);
}}

private Map<String, Object> dispatch(String name, Map<String, Object> request) {{
switch (name) {{
{runs}
default: return null;
}}
}}
}}
"""
    return files


def _flow_service(pkg, flow):
    cls = camel(flow.name) + 'Flow'
    method = lower_camel(flow.name)
    logic = flow_method(flow, name=method, indent='')
    logic = logic.replace('public static Map<String, Object>', 'static Map<String, Object>', 1)
    return f'''package {pkg}.flows;

import java.util.*;
import org.springframework.stereotype.Service;
import {pkg}.ports.ServiceRouter;
import {pkg}.runtime.R;

/**
 * {flow.name}: {flow.intent or "generated flow"}
 * Trigger: {trigger_line(flow)}. Mode: {flow.mode}.
 * Generated by Danta from IR2. Regenerate rather than edit by hand.
 */
@Service
public class {cls} {{
private final R.Services services;
private final R.Store store;
private final R.Notifier notifier;
private final R.Query query;
private final R.Publisher publisher;

public {cls}(ServiceRouter services, R.Store store, R.Notifier notifier, R.Query query, R.Publisher publisher) {{
this.services = services;
this.store = store;
this.notifier = notifier;
this.query = query;
this.publisher = publisher;
}}

/** Run the flow once; failures come back as an error result. */
public Map<String, Object> run(Map<String, Object> request) {{
return R.execute({cls}::{method}, request, new R.IO(services, store, notifier, query, publisher));
}}

{logic}
}}
'''


def _controller(pkg, system):
    http = [f for f in system.flows if f.trigger().source == 'http']
    if not http:
        return None
    fields, params, assigns, methods = [], [], [], []
    for f in http:
        cls, var = camel(f.name) + 'Flow', lower_camel(f.name)
        fields.append(f'private final {cls} {var};')
        params.append(f'{cls} {var}')
        assigns.append(f'this.{var} = {var};')
        t = f.trigger()
        mapping = {'GET': 'GetMapping', 'POST': 'PostMapping', 'PUT': 'PutMapping', 'DELETE': 'DeleteMapping'}[t.config['method']]
        if f.mode == 'async':
            body = (f'Map<String, Object> request = orEmpty(body);\n'
                    f'executor.execute(() -> {var}.run(request));\n'
                    f'return ResponseEntity.accepted().body(Map.of("accepted", true));')
        else:
            body = f'return respond({var}.run(orEmpty(body)));'
        methods.append(f'/** {f.name}{": " + f.intent if f.intent else ""} */\n'
                       f'@{mapping}({jstr(t.config["path"])})\n'
                       f'public ResponseEntity<Object> {var}(@RequestBody(required = false) Map<String, Object> body) {{\n'
                       f'{body}\n}}')
    imports = '\n'.join(f'import {pkg}.flows.{camel(f.name)}Flow;' for f in http)
    return f'''package {pkg}.web;

import java.util.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
{imports}

/** One endpoint per HTTP-triggered flow. Errors from a flow answer 422 with its response. */
@RestController
public class FlowController {{
private final TaskExecutor executor;
{chr(10).join(fields)}

public FlowController(@Qualifier("applicationTaskExecutor") TaskExecutor executor, {", ".join(params)}) {{
this.executor = executor;
{chr(10).join(assigns)}
}}

{chr(10).join(methods)}

@ExceptionHandler({{ClassCastException.class, NullPointerException.class}})
public ResponseEntity<Object> badRequest(RuntimeException e) {{
return ResponseEntity.badRequest().body(Map.of("error", "missing or malformed field"));
}}

private static Map<String, Object> orEmpty(Map<String, Object> body) {{
return body == null ? new LinkedHashMap<>() : body;
}}

@SuppressWarnings("unchecked")
private static ResponseEntity<Object> respond(Map<String, Object> result) {{
Object response = result.get("response");
if ("ok".equals(result.get("status"))) return ResponseEntity.ok(response == null ? Map.of() : response);
Map<String, Object> error = new LinkedHashMap<>();
error.put("error", result.get("error"));
if (response != null) error.putAll((Map<String, Object>) response);
return ResponseEntity.unprocessableEntity().body(error);
}}
}}
'''


def _events(pkg, system):
    ev = [f for f in system.flows if f.trigger().source == 'event']
    files = {'events/FlowEvent.java': f'''package {pkg}.events;

import java.util.Map;

/** Publish with Spring's ApplicationEventPublisher: publisher.publishEvent(new FlowEvent("name", payload)). */
public record FlowEvent(String name, Map<String, Object> payload) {{}}
'''}
    files['events/TopicMessage.java'] = f'''package {pkg}.events;

import java.util.Map;

/** A message on a topic, as published by a flow. */
public record TopicMessage(String topic, Map<String, Object> message) {{}}
'''
    topics = [f for f in system.flows if f.trigger().source == 'topic']
    if topics:
        tfields, tparams, tassigns, tmethods = [], [], [], []
        for f in topics:
            cls, var = camel(f.name) + 'Flow', lower_camel(f.name)
            topic = f.trigger().config['name']
            tfields.append(f'private final {cls} {var};')
            tparams.append(f'{cls} {var}')
            tassigns.append(f'this.{var} = {var};')
            tmethods.append(f'@EventListener(condition = "#m.topic == \'{topic}\'")\n'
                            f'public void {var}(TopicMessage m) {{\n{var}.run(new LinkedHashMap<>(m.message()));\n}}')
        timports = '\n'.join(f'import {pkg}.flows.{camel(f.name)}Flow;' for f in topics)
        files['events/TopicListeners.java'] = f'''package {pkg}.events;

import java.util.LinkedHashMap;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
{timports}

/** Runs the flow subscribed to each topic. */
@Component
public class TopicListeners {{
{chr(10).join(tfields)}

public TopicListeners({", ".join(tparams)}) {{
{chr(10).join(tassigns)}
}}

{chr(10).join(tmethods)}
}}
'''
    if not ev:
        return files
    fields, params, assigns, methods = [], [], [], []
    for f in ev:
        cls, var = camel(f.name) + 'Flow', lower_camel(f.name)
        name = f.trigger().config['name']
        fields.append(f'private final {cls} {var};')
        params.append(f'{cls} {var}')
        assigns.append(f'this.{var} = {var};')
        methods.append(f'@EventListener(condition = "#event.name == \'{name}\'")\n'
                       f'public void on{camel(name)}(FlowEvent event) {{\n{var}.run(event.payload());\n}}')
    imports = '\n'.join(f'import {pkg}.flows.{camel(f.name)}Flow;' for f in ev)
    files['events/FlowEventListeners.java'] = f'''package {pkg}.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
{imports}

/** Runs the flow listening for each event. */
@Component
public class FlowEventListeners {{
{chr(10).join(fields)}

public FlowEventListeners({", ".join(params)}) {{
{chr(10).join(assigns)}
}}

{chr(10).join(methods)}
}}
'''
    return files


def _schedule(pkg, system):
    sc = [f for f in system.flows if f.trigger().source == 'schedule']
    if not sc:
        return None
    fields, params, assigns, methods = [], [], [], []
    for f in sc:
        cls, var = camel(f.name) + 'Flow', lower_camel(f.name)
        t = f.trigger()
        vals = ', '.join(f'{jstr(n)}, ' + ('LocalDate.now().toString()' if ft == STR else
                                            '0' if ft == INT else 'false' if ft == BOOL else 'new ArrayList<>()')
                         for n, ft in t.payload.fields)
        fields.append(f'private final {cls} {var};')
        params.append(f'{cls} {var}')
        assigns.append(f'this.{var} = {var};')
        methods.append(f'/** Unix cron "{t.config["cron"]}". Edit the payload to suit. */\n'
                       f'@Scheduled(cron = {jstr(spring_cron(t.config["cron"]))})\n'
                       f'public void {var}() {{\n{var}.run(R.map({vals}));\n}}')
    imports = '\n'.join(f'import {pkg}.flows.{camel(f.name)}Flow;' for f in sc)
    return f'''package {pkg}.schedule;

import java.time.LocalDate;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import {pkg}.runtime.R;
{imports}

/** Runs each scheduled flow on its cron, unless RUN_SCHEDULER=0 (exactly one instance should run it). */
@Component
@ConditionalOnProperty(name = "RUN_SCHEDULER", havingValue = "1", matchIfMissing = true)
public class ScheduledFlows {{
{chr(10).join(fields)}

public ScheduledFlows({", ".join(params)}) {{
{chr(10).join(assigns)}
}}

{chr(10).join(methods)}
}}
'''


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------

def _flow_test(pkg, flow):
    cls = camel(flow.name) + 'Flow'
    method = lower_camel(flow.name)
    keys = ', '.join(f'Map.entry({jstr(e)}, {jstr(rec.fields[0][0])})' for e, rec in flow.entities.items())
    return f'''package {pkg}.flows;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.*;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import {pkg}.runtime.R;

/** {flow.name}: every generated scenario, replayed. Generated from the reference simulator. */
class {cls}Test {{
private static final ObjectMapper JSON = new ObjectMapper();
private static final Map<String, String> KEYS = Map.ofEntries({keys});

@SuppressWarnings("unchecked")
@TestFactory
Stream<DynamicTest> scenarios() throws Exception {{
Map<String, Object> scenarios;
try (InputStream in = getClass().getResourceAsStream("/scenarios/{flow.name}.json")) {{
scenarios = JSON.readValue(in, Map.class);
}}
return scenarios.entrySet().stream().map(e -> DynamicTest.dynamicTest(e.getKey(), () -> {{
Map<String, Object> sc = (Map<String, Object>) e.getValue();
Map<String, Object> mocks = (Map<String, Object>) sc.getOrDefault("mocks", Map.of());
List<Object> effects = new ArrayList<>();
Map<String, Integer> attempts = new HashMap<>();
Map<String, List<Map<String, Object>>> rows = new HashMap<>();
((Map<String, List<Map<String, Object>>>) sc.getOrDefault("store", Map.of())).forEach((k, v) -> rows.put(k, new ArrayList<>(v)));
R.Services services = (service, op, args, step) -> {{
int n = attempts.merge(step, 1, Integer::sum);
Object m = mocks.get(step);
List<Object> outcomes = m instanceof List ? (List<Object>) m : List.of(m);
Map<String, Object> outcome = (Map<String, Object>) outcomes.get(Math.min(n, outcomes.size()) - 1);
effects.add("call " + service + "." + op + " #" + n);
if (outcome.containsKey("ok")) return JSON.convertValue(outcome.get("ok"), Map.class);
throw new R.ServiceError((String) outcome.get("error"));
}};
R.Store store = (entity, op, data) -> {{
effects.add("persist " + entity + "." + op);
List<Map<String, Object>> table = rows.computeIfAbsent(entity, k -> new ArrayList<>());
if (op.equals("create")) {{
table.add(new LinkedHashMap<>(data));
return;
}}
String key = KEYS.get(entity);
table.removeIf(r -> Objects.equals(r.get(key), data.get(key)));
if (op.equals("update")) table.add(new LinkedHashMap<>(data));
}};
R.Query query = (entity, where) -> {{
List<Object> found = new ArrayList<>();
for (Map<String, Object> r : rows.getOrDefault(entity, List.of()))
if (where.entrySet().stream().allMatch(w -> Objects.equals(r.get(w.getKey()), w.getValue()))) found.add(new LinkedHashMap<>(r));
return found;
}};
R.Publisher publisher = (topic, message) -> {{
try {{
effects.add("publish " + topic + " " + JSON.writeValueAsString(message));
}} catch (Exception ex) {{
throw new IllegalStateException(ex);
}}
}};
R.Notifier notifier = (channel, to, message) -> effects.add("notify " + channel + " " + to + ": " + message);
Map<String, Object> input = JSON.convertValue(sc.get("input"), Map.class);
Map<String, Object> result = R.execute({cls}::{method}, input, new R.IO(services, store, notifier, query, publisher));
Map<String, Object> want = (Map<String, Object>) sc.get("expect");
assertEquals(want.get("status"), result.get("status"), "status");
assertEquals(want.get("response"), result.get("response"), "response");
assertEquals(want.get("effects"), effects, "effects");
}}));
}}
}}
'''


def _app_test(pkg, system):
    http = [f for f in system.flows if f.trigger().source == 'http']
    checks = []
    for f in http:
        t = f.trigger()
        scenarios = system.scenarios.get(f.name, {})
        if not scenarios:
            continue
        payload = json.dumps(next(iter(scenarios.values()))['input'])
        verb = {'GET': 'get', 'POST': 'post', 'PUT': 'put', 'DELETE': 'delete'}[t.config['method']]
        matcher = 'status().isAccepted()' if f.mode == 'async' else 'status().is(anyOf(equalTo(200), equalTo(422)))'
        checks.append(f'mvc.perform({verb}({jstr(t.config["path"])}).contentType(MediaType.APPLICATION_JSON)'
                      f'.content({jstr(payload)})).andExpect({matcher});')
    body = '\n'.join(checks) or '// no HTTP-triggered flows'
    return f'''package {pkg};

import static org.hamcrest.Matchers.anyOf;
import static org.hamcrest.Matchers.equalTo;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** The application starts, the API documents are served, and every HTTP trigger answers
 *  (with the stand-ins in place). */
@SpringBootTest
@AutoConfigureMockMvc
class ApplicationTests {{
@Autowired
private MockMvc mvc;

@Test
void openApiDocumentAndSwaggerUi() throws Exception {{
mvc.perform(get("/openapi.json")).andExpect(status().isOk());
mvc.perform(get("/swagger-ui/index.html")).andExpect(status().isOk());
}}

@Test
void httpTriggersAnswer() throws Exception {{
{body}
}}
}}
'''


def _readme(system, pkg):
    lines = [f'# {system.name}', '']
    if system.description:
        lines += [system.description, '']
    lines += ['A Spring Boot 3 application generated by Danta from a Danta Spec. Every flow was',
              'verified against the reference simulator; `src/test` replays those scenarios, so keep them',
              'passing when you edit. Java 17+.', '', '## Flows', '']
    for f in system.flows:
        lines += [f'### {f.name}', '', f'`{trigger_line(f)}`, {f.mode}.', '']
        if f.intent:
            lines += [f.intent, '']
        lines += outline(f) + ['']
    lines += infra.readme_section(system, 8080, '`mvn spring-boot:run`.')
    lines += frontend.readme_section(system, 8080)
    lines += ['## Run', '', '```bash', 'mvn test', 'mvn spring-boot:run            # http://localhost:8080/docs', '```', '',
              '## API and topics', '',
              '- **HTTP:** Swagger UI at `/docs`, showing `src/main/resources/static/openapi.json`, the',
              '  OpenAPI document generated from the spec.',
              '- **Topics:** `docs/asyncapi.json` lists every topic, who publishes to it and who consumes it.', '',
              '## Connect real systems', '',
              'Each outside system is a Spring bean with a stand-in:', '',
              f'- services: implement the interfaces in `src/main/java/{pkg}/ports/` (the `Fake*` classes in',
              '  `adapters/` stand in until you do);',
              '- storage: provide an `R.Store` bean (the stand-in is `InMemoryStore`);',
              '- notifications: provide an `R.Notifier` bean (the stand-in is `LoggingNotifier`).', '',
              'Mark your bean `@Primary`, or delete the stand-in.', '',
              'Parallel steps run one after another, in the order written. Integers are Java `int`',
              '(money in cents) and wrap on overflow, exactly as in the spec. Scheduled flows use the',
              'spec\'s cron with a leading seconds field added, as Spring requires.', '']
    return '\n'.join(lines)


def _data_controller(pkg, data):
    entries = ',\n'.join(
        f'Map.entry({jstr(e)}, Map.ofEntries(' + ', '.join(f'Map.entry({jstr(n)}, {jstr(t)})' for n, t in fields.items()) + '))'
        for e, fields in data.items())
    return f"""package {pkg}.web;

import java.util.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import {pkg}.runtime.R;

/** The records the frontend's list screens read: GET /data/<entity>?field=value&... */
@RestController
@RequestMapping("/data")
public class DataController {{
private static final Map<String, Map<String, String>> FIELDS = Map.ofEntries(
{entries});

private final R.Query query;

public DataController(R.Query query) {{
this.query = query;
}}

@GetMapping("/{{entity}}")
public ResponseEntity<Object> records(@PathVariable String entity, @RequestParam Map<String, String> params) {{
Map<String, String> fields = FIELDS.get(entity);
if (fields == null) {{
return ResponseEntity.status(404).body(Map.of("error", "no screen lists " + entity));
}}
Map<String, Object> where = new LinkedHashMap<>();
for (Map.Entry<String, String> p : params.entrySet()) {{
String type = fields.get(p.getKey());
if (type == null) {{
return ResponseEntity.badRequest().body(Map.of("error", entity + " has no field " + p.getKey()));
}}
try {{
where.put(p.getKey(), switch (type) {{
case "int" -> Integer.parseInt(p.getValue());
case "bool" -> Boolean.parseBoolean(p.getValue());
default -> p.getValue();
}});
}} catch (NumberFormatException e) {{
return ResponseEntity.badRequest().body(Map.of("error", p.getKey() + " must be a whole number"));
}}
}}
return ResponseEntity.ok(query.query(entity, where));
}}
}}
"""


def generate(system):
    pkg = snake(system.name)
    namer = collect_types(system)
    root = system.name
    main = f'{root}/src/main/java/{pkg}'
    test = f'{root}/src/test/java/{pkg}'
    files = {
        f'{root}/pom.xml': f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{SPRING_BOOT}</version>
    <relativePath/>
  </parent>
  <groupId>generated</groupId>
  <artifactId>{system.name}</artifactId>
  <version>0.1.0</version>
  <description>{(system.description or 'Generated by Danta')[:200]}</description>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.mongodb</groupId>
      <artifactId>mongodb-driver-sync</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springdoc</groupId>
      <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
      <version>{SPRINGDOC}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
''',
        f'{root}/README.md': _readme(system, pkg),
        f'{root}/src/main/resources/application.properties': (
            f'spring.application.name={system.name}\n'
            'spring.main.banner-mode=off\n'
            '# Swagger UI shows the OpenAPI document generated from the spec (static/openapi.json)\n'
            'springdoc.swagger-ui.url=/openapi.json\n'
            'springdoc.swagger-ui.path=/docs\n'
            'springdoc.api-docs.path=/v3/api-docs\n'
            'server.port=${PORT:8080}\n'
            '# Adapters build their own clients from MONGO_URL, RABBITMQ_URL and SMTP_* (see adapters/),\n'
            '# switched on by STORE=mongo, BROKER=rabbitmq and NOTIFY=smtp; Spring\'s own auto-configuration\n'
            '# for them stays off, so tests never need the infrastructure.\n'
            'spring.autoconfigure.exclude='
            'org.springframework.boot.autoconfigure.mongo.MongoAutoConfiguration,'
            'org.springframework.boot.autoconfigure.data.mongo.MongoDataAutoConfiguration,'
            'org.springframework.boot.autoconfigure.amqp.RabbitAutoConfiguration,'
            'org.springframework.boot.autoconfigure.mail.MailSenderAutoConfiguration\n'),
        f'{root}/Dockerfile': JAVA_DOCKERFILE,
        f'{root}/.dockerignore': 'target\n.git\n',
        f'{root}/docker-compose.yml': infra.compose(system, 8080, 'java'),
        f'{root}/.env.example': infra.env_example(system, 8080),
        f'{root}/src/main/resources/static/openapi.json': json.dumps(openapi(system), indent=2) + '\n',
        f'{root}/docs/asyncapi.json': json.dumps(asyncapi(system), indent=2) + '\n',
        f'{main}/Application.java': f'''package {pkg};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/** {system.name} - generated by Danta. */
@SpringBootApplication
@EnableScheduling
public class Application {{
public static void main(String[] args) {{
SpringApplication.run(Application.class, args);
}}
}}
''',
        f'{main}/runtime/R.java': (f'package {pkg}.runtime;\n\nimport java.math.BigInteger;\nimport java.util.*;\n\n'
                                   '/** Shared runtime for the generated flows: results, service calls, 32-bit arithmetic. */\n'
                                   f'public final class R {{{RUNTIME}}}\n'),
        f'{main}/Models.java': _models(pkg, namer),
        f'{test}/ApplicationTests.java': _app_test(pkg, system),
    }
    for path, content in {**_ports(pkg, system, namer), **_adapters(pkg, system, namer), **_events(pkg, system),
                          **_real_adapters(pkg, system)}.items():
        files[f'{main}/{path}'] = content
    controller = _controller(pkg, system)
    if controller:
        files[f'{main}/web/FlowController.java'] = controller
    if data_entities(system):
        files[f'{main}/web/DataController.java'] = _data_controller(pkg, data_entities(system))
    schedule = _schedule(pkg, system)
    if schedule:
        files[f'{main}/schedule/ScheduledFlows.java'] = schedule
    for f in system.flows:
        files[f'{main}/flows/{camel(f.name)}Flow.java'] = _flow_service(pkg, f)
        files[f'{test}/flows/{camel(f.name)}FlowTest.java'] = _flow_test(pkg, f)
        files[f'{root}/src/test/resources/scenarios/{f.name}.json'] = json.dumps(
            system.scenarios.get(f.name, {}), indent=2) + '\n'
    files.update(frontend.generate_web(system, 8080))
    files.update({f'{root}/{k}': v for k, v in deploy.manifests(system, 8080, 'IMAGE').items()})
    return files
