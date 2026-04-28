package com.github.juanfernandez.article;

import com.github.juanfernandez.article.pregunta.application.PreguntaGeneratorService;
import com.github.juanfernandez.article.pregunta.infrastructure.persistence.JpaPreguntaRepository;
import com.github.juanfernandez.article.pregunta.port.in.PreguntaGeneratorPort;
import com.github.juanfernandez.article.pregunta.port.out.PreguntaRepositoryPort;
import com.github.juanfernandez.article.shared.ai.port.AiPort;
import com.github.juanfernandez.article.shared.util.JsonUtils;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

/**
 * Spring Boot auto-configuration for the optional Question Generator feature.
 *
 * <p>This configuration is completely independent of {@link ArticleGeneratorAutoConfiguration}
 * and is only activated when a {@link JpaPreguntaRepository} bean is present in the application
 * context (which requires {@code spring-boot-starter-data-jpa} and a configured
 * {@code DataSource} in the consuming application).
 *
 * <h2>Hexagonal architecture</h2>
 * <ul>
 *   <li><strong>Input port</strong>: {@link PreguntaGeneratorPort} — the use case interface
 *       consumed by application code.</li>
 *   <li><strong>Output port</strong>: {@link PreguntaRepositoryPort} — persistence abstraction
 *       implemented by {@link JpaPreguntaRepository}.</li>
 *   <li><strong>Application service</strong>: {@link PreguntaGeneratorService} — orchestrates
 *       the use case, depends only on the port interfaces.</li>
 * </ul>
 *
 * <h2>Activation</h2>
 * <p>Add to your project:
 * <pre>
 * &lt;dependency&gt;
 *     &lt;groupId&gt;org.springframework.boot&lt;/groupId&gt;
 *     &lt;artifactId&gt;spring-boot-starter-data-jpa&lt;/artifactId&gt;
 * &lt;/dependency&gt;
 * </pre>
 * and define a {@code JpaPreguntaRepository} bean (or let Spring Data JPA create it
 * automatically when the {@code Pregunta} entity is scanned).
 */
@AutoConfiguration(after = ArticleGeneratorAutoConfiguration.class)
public class PreguntaGeneratorAutoConfiguration {

    /**
     * Registers {@link PreguntaGeneratorService} when a {@link JpaPreguntaRepository} bean is
     * present and no {@link PreguntaGeneratorPort} bean has been defined by the application.
     *
     * @param aiPort               shared AI port bean from {@link ArticleGeneratorAutoConfiguration}
     * @param preguntaRepository   Spring Data JPA repository for the {@code preguntas} table
     * @return fully configured {@link PreguntaGeneratorService}
     */
    @Bean
    @ConditionalOnMissingBean(PreguntaGeneratorPort.class)
    @ConditionalOnBean(JpaPreguntaRepository.class)
    public PreguntaGeneratorService preguntaGeneratorService(AiPort aiPort,
                                                              JpaPreguntaRepository preguntaRepository,
                                                              JsonUtils jsonUtils) {
        return new PreguntaGeneratorService(aiPort, preguntaRepository, jsonUtils);
    }
}
